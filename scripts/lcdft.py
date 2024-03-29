import sys
from PyQt5 import QtCore, QtGui, uic, QtWidgets
import breeze_resources
import pyqtgraph as pg
import pandas as pd
import numpy as np
from astropy import units as u
import os
from boxcar import smooth as bcsmooth
import subprocess
from freqs_plot import create_freqs
import pet

dir_path = os.path.realpath(__file__).replace(__file__.split('/')[-1], '')
temp_path = dir_path+".temp_lcView/"

qtCreatorFile = dir_path + "lcdft.ui"  # Enter file here.
Ui_MainWindow, QtBaseClass = uic.loadUiType(qtCreatorFile)


class TableModel(QtCore.QAbstractTableModel):
    def __init__(self):
        super(TableModel, self).__init__()
        self.datatable = None
        self.colLabels = None

    def update_tm(self, datain):
        # print('Updating Model')
        self.datatable = datain
        self.colLabels = datain.columns.values

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self.datatable.index)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return len(self.datatable.columns.values)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        i = index.row()
        j = index.column()
        index_data = self.datatable.iloc[i][j]
        if role == QtCore.Qt.DisplayRole:
            return '{0}'.format(index_data)
        else:
            return QtCore.QVariant()

    def flags(self, index):
        return QtCore.Qt.ItemIsEnabled

    def headerData(self, section, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return QtCore.QVariant(self.colLabels[section])
        if orientation == QtCore.Qt.Vertical and role == QtCore.Qt.DisplayRole:
            return QtCore.QVariant("%s" % str(section + 1))
        return QtCore.QVariant()


class lcdftMain(QtGui.QMainWindow, Ui_MainWindow):

    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        Ui_MainWindow.__init__(self)
        pg.setConfigOptions(antialias=True)
        self.showMaximized()
        self.setupUi(self)

        # ------------------------------ Tree View ---------------------------------- #
        self.popmodel = QtWidgets.QFileSystemModel()
        self.populate()
        self.treeView.clicked.connect(self.onClicked)
        # --------------------------------------------------------------------------- #

        # ------------------------------ Phase Slider------------------------------- #
        self.phase_slider.valueChanged.connect(self.phase_shift)
        # --------------------------------------------------------------------------- #

        self.dir_path = os.path.realpath(__file__).replace(__file__.split('/')[-1],
                                                           '')  # path to directory where app is opened
        # Initialize pens
        self.symredpen = "#ff000d"
        self.symbckpen = (24, 24, 24)
        self.symwhipen = (240, 240, 240)
        self.symtrapen = (240, 240, 240, 0)
        self.symgrepen = "#76cd26"
        self.symyelpen = "#fffe7a"
        self.symyelpen = "#b04e0f"
        self.symblupen = "#047495"

        self.redpen = pg.mkPen(color=self.symredpen, width=2.2)
        self.bckpen = pg.mkPen(color=self.symbckpen)
        self.whipen = pg.mkPen(color=self.symwhipen)
        self.grepen = pg.mkPen(color=self.symgrepen)
        self.grelin = pg.mkPen(color=self.symgrepen, style=QtCore.Qt.DotLine)
        self.yelpen = pg.mkPen(color=self.symyelpen, width=0.3)
        self.blupen = pg.mkPen(color=self.symblupen, width=0.3)
        self.trapen = pg.mkPen(color=self.symtrapen, width=0.3)
        
        self.bg_color = '#1C1717'
        self.sympen = self.symwhipen
        light = True
        if light:
            self.bg_color = '#FFFFFF'
            self.sympen = self.symbckpen
    

        # Initialize plots to connect with mouse

        self.ph.setBackground(self.bg_color)
        # self.ph.plotItem.setLabel('left', "Flux/Magnitude")#, units='ppt/mmag')
        # self.ph.plotItem.setLabel('bottom', "Phase")
       
        self.lc.setBackground(self.bg_color)
        self.lc.plotItem.setLabel('left', "Flux/Magnitude")#, units='ppt/mmag')
        self.lc.plotItem.setLabel('bottom', "Time")#, units='d')

        self.dft.setBackground(self.bg_color)
        self.dft.plotItem.setLabel('left', "Amplitude")#, units='ppt/mmag')
        self.dft.plotItem.setLabel('bottom', "Frequency")#, units='1/d')

        self.tabWidget.currentChanged.connect(self.show_phase_labels) # Workaround for error when self.ph labels are set above

        self.curve_lc = self.lc.plot(x=[], y=[], pen=None, symbol='o', symbolSize=3, symbolPen=self.sympen,
                                     symbolBrush=self.sympen)    
        self.err_lc = pg.ErrorBarItem(x=np.array([]), y=np.array([]), height=np.array([]), beam=0.0,
                                      pen={'color': 'w', 'width': 0.85})    
        self.lc.addItem(self.err_lc)
      
        
        self.curve_ph = self.ph.plot(x=[], y=[], pen=None, symbol='o', symbolSize=3, symbolPen=self.sympen,
                                     symbolBrush=self.sympen)                           
        self.err_ph = pg.ErrorBarItem(x=np.array([]), y=np.array([]), height=np.array([]), beam=0.0,
                                      pen={'color': 'w', 'width': 0.85})
        self.ph.addItem(self.err_ph)              
        self.curve_ph_smooth = self.ph.plot(x=[], y=[], pen=None, symbol='o', symbolSize=4, symbolPen=self.symgrepen,
                                            symbolBrush=self.symgrepen)

        self.curve_dft = self.dft.plot(x=[], y=[], pen=self.sympen)
        self.check_freq() # Check if freq exists and set [not]checkable QCheckBox for frequencies

        # --------------------------- Mouse position -------------------------------- #
        # Show positions of the mouse
        self.curve_lc.scene().sigMouseMoved.connect(self.onMouseMoved)
        self.curve_ph.scene().sigMouseMoved.connect(self.onMouseMoved)
        self.curve_dft.scene().sigMouseMoved.connect(self.onMouseMoved)
        # --------------------------------------------------------------------------- #

        # Get position from click
        self.mouse_x = 1.
        self.mouse_y = 1.
        self.curr_per = 1. / self.mouse_x
        self.curr_ampl = 1. / self.mouse_y
        self.curve_dft.scene().sigMouseClicked.connect(self.onMouseClicked)

        # Initialize variables for dft range
        self.startf = self.start_spin.value()
        self.endf = self.end_spin.value()
        self.acc = self.acc_spin.value()


        # Initialize variables
        self.shift_p = 0
        self.current_point = [0]  # sigMouseClicked and sigMouseMoved give different values (moved is correct)
        self.time, self.flux, self.ferr = [0, 0, 0]
        self.ferr_ph, self.flux_ph, self.flux_smoothed, self.phase = [0, 0, 0, 0]
        self.freq, self.ampl = [0, 0]
        self.nofphases = int(self.phase_dial.value())
        self.size_to_find = 100*self.acc # in points; to find max. peak 

        # ------------------------------ Graphics ----------------------------------- #
        self.file_path = 'first_run'  # path to recognize when first run
        self.max_per = 1.
        self.errors.stateChanged.connect(self.error_changed)
        self.smooth.stateChanged.connect(self.smooth_changed)
        self.invertyaxis.stateChanged.connect(self.invertyaxis_changed)
        self.hide_phase.stateChanged.connect(self.hide_phase_changed)
        self.smooth_spin.valueChanged.connect(self.smooth_changed)
        self.start_spin.valueChanged.connect(self.getdftrange)
        self.end_spin.valueChanged.connect(self.getdftrange)
        self.acc_spin.valueChanged.connect(self.getdftrange)
        self.recalcbutton.clicked.connect(self.onClicked)
        self.phasebutton.clicked.connect(self.phase_clicked)
        self.addfreqbutton.clicked.connect(self.add_clicked)
        self.remfreqbutton.clicked.connect(self.rem_clicked)
        self.phase_dial.valueChanged.connect(self.phase_dial_changed)
        self.freq_comb.stateChanged.connect(lambda: self.freq_visibility("com"))
        self.freq_ind.stateChanged.connect(lambda: self.freq_visibility("ind"))
        
        self.petbutton.clicked.connect(self.petbutton_clicked)


        self.stylecombobox.addItems(["Light Mode", "Dark Mode"])
        self.stylecombobox.activated[str].connect(self.selectionchange)
        # --------------------------------------------------------------------------- #

        # -------------------- Start table with frequency data ---------------------- #
        #                                                                             #
        self.freq_cdf = pd.DataFrame(data={'Frequency': [], 'Period': []})  # Create table data
        # freq_cdf = df = pd.DataFrame(data={'Frequency': [], 'Period': [], 'Amplitude': []})  # Create table data
        self.freqtm = TableModel()  # Create table model
        self.freqtm.update_tm(self.freq_cdf)
        self.freqtv = self.freq_list
        self.freqtv.setModel(self.freqtm)
        self.freqtv.horizontalHeader().setResizeMode(QtGui.QHeaderView.Stretch)
        self.freqtv.clicked.connect(self.table_clicked)
        # self.freqtv.setSortingEnabled(True)

        # self.freqtv.resizeColumnsToContents()
        # self.freqtv.resizeRowsToContents()
        #                                                                             #
        # --------------------------------------------------------------------------- #

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_F:
            point = self.current_point
            tt = self.current_point
            xx = self.dft.plotItem.vb.mapSceneToView(tt).x()
            yy = self.dft.plotItem.vb.mapSceneToView(tt).y()
            self.mouse_x = xx
            try:
                xx_ind = np.where(np.abs(self.freq - xx) < 0.001)[0][0]
                arg_max = np.argmax(self.ampl[xx_ind-self.size_to_find:xx_ind+self.size_to_find])
                self.curr_per = 1. / self.freq[xx_ind+arg_max-self.size_to_find]
            except IndexError:
                pass
            self.update_line()  # update vertical line
            self.phase_slider.setValue(499)  # reset phase shifter
            self.phase_spin.setValue(1. / self.curr_per)
            self.plot_ph()  # update phase plot
            self.error_changed()
            self.smooth_changed()
            self.hide_phase_changed()
            # self.ph.autoRange()
            self.lc.autoRange()
            self.nyq_and_per()    
            # elif event.key() == QtCore.Qt.Key_Enter:
        #     self.proceed()
        # event.accept()

    def petbutton_clicked(self):
        new_gui = subprocess.Popen(["python", dir_path+"pet.py", self.file_path.rsplit("/", 1)[0]])

    def freq_visibility(self, ftype):
        if ftype == "com":
            df = self.freq_com_df
            cb = self.freq_comb
            self.fl = self.com_freqs
            line_color = self.yelpen
        if ftype == "ind":
            df = self.freq_ind_df
            cb = self.freq_ind
            self.fl = self.ind_freqs
            line_color = self.blupen

        subscript = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
        if cb.checkState() == 0:
            for cfl in self.fl:
                self.dft.removeItem(cfl)
        elif cb.checkState() == 1:
            self.fl = []
            for freq, label in zip(df['freq'], df['label']):
                if ftype == "com":
                    formatted_label = label.translate(subscript)
                if ftype == "ind":
                    formatted_label = label.split('_')[0]+label.split('_')[1].strip("{").strip("}").translate(subscript)
                freq_line = pg.InfiniteLine(pos=freq, pen=line_color, span=(0.9,1), label=formatted_label, labelOpts={"position":0.5})
                freq_line.addMarker('v', position=0, size=10.0)
                self.fl.append(freq_line)
                self.dft.addItem(freq_line)
        elif cb.checkState() == 2:
            try:
                for cfl in self.fl:
                    self.dft.removeItem(cfl)
            except AttributeError:
                pass
            self.fl = []
            for freq, label in zip(df['freq'], df['label']):
                if ftype == "com":
                    formatted_label = label.translate(subscript)
                if ftype == "ind":
                    formatted_label = label.split('_')[0]+label.split('_')[1].strip("{").strip("}").translate(subscript)
                freq_line = pg.InfiniteLine(pos=freq, pen=line_color, label=formatted_label, labelOpts={"position":0.95})
                freq_line.addMarker('v', position=0.9, size=10.0)
                self.fl.append(freq_line)
                self.dft.addItem(freq_line)
        if ftype == "com":
            self.com_freqs = self.fl
        if ftype == "ind":
            self.ind_freqs = self.fl

    def show_phase_labels(self):
        self.ph.plotItem.setLabel('left', "Flux/Magnitude")#, units='ppt/mmag')
        self.ph.plotItem.setLabel('bottom', "Phase")

    def check_freq(self):
        try:
            full_path=str(self.file_path).rsplit("/", 1)[0]+"/"
            # print(full_path)
            self.freq_exists = create_freqs(temp_path, full_path)
        except AttributeError:
            self.freq_exists = False
        if self.freq_exists:
            self.freq_ind.setCheckable(True)
            self.freq_ind.setChecked(True)
            self.freq_ind.setStyleSheet("QCheckBox{color: black}")
            
            # self.freq_harm.setCheckable(True)
            # self.freq_harm.setChecked(True)
            # self.freq_harm.setStyleSheet("QCheckBox{color: black}")
            self.freq_harm.setCheckable(False)
            self.freq_harm.setStyleSheet("QCheckBox{color: gray}")
            
            self.freq_comb.setCheckable(True)
            self.freq_comb.setChecked(True)
            self.freq_comb.setStyleSheet("QCheckBox{color: black}")

            self.freq_ind_df = pd.read_csv(temp_path+'freqs_plot', header=None, names=["freq", "label"], sep='\s+')
            self.freq_com_df = pd.read_csv(temp_path+'combs_plot', header=None, names=["freq", "label"], sep='\s+')
            try:
                for ifl in self.ind_freqs:
                    self.dft.removeItem(ifl)
            except AttributeError:
                pass

            try:
                for cfl in self.com_freqs:
                    self.dft.removeItem(cfl)
            except AttributeError:
                pass

            subscript = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
           
            self.ind_freqs = []
            self.com_freqs = []
            for com_freq, com_label in zip(self.freq_com_df['freq'], self.freq_com_df['label']):
                com_freq_line = pg.InfiniteLine(pos=com_freq, pen=self.yelpen, label=com_label.translate(subscript), labelOpts={"position":0.95})
                com_freq_line.addMarker('v', position=0.9, size=10.0)
                self.com_freqs.append(com_freq_line)
                self.dft.addItem(com_freq_line)
            for ind_freq, ind_label in zip(self.freq_ind_df['freq'], self.freq_ind_df['label']):
                formatted_label = ind_label.split('_')[0]+ind_label.split('_')[1].strip("{").strip("}").translate(subscript)
                ind_freq_line = pg.InfiniteLine(pos=ind_freq, pen=self.blupen, label=formatted_label, labelOpts={"position":0.95})
                ind_freq_line.addMarker('v', position=0.9, size=10.0)
                self.ind_freqs.append(ind_freq_line)
                self.dft.addItem(ind_freq_line)

        else:
            try:
                for ifl in self.ind_freqs:
                    self.dft.removeItem(ifl)
            except AttributeError:
                pass

            try:
                for cfl in self.com_freqs:
                    self.dft.removeItem(cfl)
            except AttributeError:
                pass

            self.freq_ind.setCheckable(False)
            self.freq_ind.setStyleSheet("QCheckBox{color: gray}")
            self.freq_harm.setCheckable(False)
            self.freq_harm.setStyleSheet("QCheckBox{color: gray}")
            self.freq_comb.setCheckable(False)
            self.freq_comb.setStyleSheet("QCheckBox{color: gray}")


    def selectionchange(self, styleName):
        if styleName == 'Light Mode':
            file = QtCore.QFile(dir_path + 'styles/light.qss')
        if styleName == 'Dark Mode':
            file = QtCore.QFile(dir_path + 'styles/dark.qss')
        file.open(QtCore.QFile.ReadOnly | QtCore.QFile.Text)
        stream = QtCore.QTextStream(file)
        self.setStyleSheet(stream.readAll())

    def phase_dial_changed(self):
        self.nofphases = int(self.phase_dial.value())
        self.plot_ph()
        self.error_changed()
        self.smooth_changed()
        self.hide_phase_changed()
        # self.ph.autoRange()

    def add_clicked(self):
        new_cdf = pd.DataFrame({'Frequency': [np.round((1. / self.curr_per), 5)], 'Period': [np.round(self.per_u, 2)]})
        self.freq_cdf = self.freq_cdf.append(new_cdf, ignore_index=True)
        self.freq_cdf.index = range(self.freq_cdf.shape[0])
        self.update_table()

    def rem_clicked(self, item):
        self.freq_cdf.index = range(self.freq_cdf.shape[0])
        self.freq_cdf = self.freq_cdf.drop(self.freq_to_remove.row())
        self.freq_to_remove = False
        self.update_table()

    def table_clicked(self, item):
        self.freq_cdf.index = range(self.freq_cdf.shape[0])
        try:
            self.phase_spin.setValue(float(item.data()))
        except ValueError:
            pass
        self.freq_to_remove = item

    def progress_bar(self):
        deltaT = np.ptp(self.time)
        self.max_progress = int((self.endf - self.startf) * self.acc * deltaT)
        self.dftprogress.setValue(int(self.wc_process / self.max_progress * 100))

    def nyq_and_per(self):
        self.nyqf = 1 /(2 * (self.time[-1] - self.time[-2]))
        self.per_u = self.curr_per * u.day
        if self.per_u.value < 1./24:
            self.per_u = self.per_u.to(u.min)
        elif self.per_u.value < 1:
            self.per_u = self.per_u.to(u.hour)
        self.nyq_lab.setText("Nyquist frequency: "+str(np.round(self.nyqf, 3))+"d<sup>-1<sup>")
        self.per_lab.setText("Current period: "+str(np.round(self.per_u, 2)))

    def phase_clicked(self):
        try:
            self.curr_per = 1. / self.phase_spin.value()
            # self.show_table()  # update frequency list
            self.plot_ph()  # update phase plot
            self.error_changed()
            self.smooth_changed()
            self.hide_phase_changed()
            self.update_line()  # update vertical line
            self.phase_slider.setValue(499)  # reset phase shifter
        except ZeroDivisionError:
            print("Phase value cannot be zero.")

    def sort_phases(self):
        temp = sorted(zip(self.phase, np.tile(self.flux, self.nofphases), np.tile(self.ferr, self.nofphases)))
        self.phase, self.flux_ph, self.ferr_ph = zip(*temp)
        self.phase = np.array(self.phase)
        self.flux_ph = np.array(self.flux_ph)
        self.ferr_ph = np.array(self.ferr_ph)

    def getdftrange(self):
        self.startf = self.start_spin.value()
        self.endf = self.end_spin.value()
        self.acc = self.acc_spin.value()
        self.size_to_find = 100*self.acc

    def phase_shift(self):
        self.shift_p = (float(self.phase_slider.value()) - 500.) / 1000. * self.curr_per
        self.plot_ph()
        # self.sort_phases()
        self.error_changed()
        self.smooth_changed()
        self.hide_phase_changed()

    def error_changed(self):
        if self.errors.isChecked():
            self.err_lc.setData(x=self.time, y=self.flux, height=self.ferr)
            self.err_ph.setData(x=self.phase, y=self.flux_ph, height=self.ferr_ph)
            self.err_lc.update()
            self.err_ph.update()
        else:
            self.err_lc.setData(x=np.array([self.time[0]]), y=np.array([self.flux[0]]), height=np.array([0]))
            self.err_ph.setData(x=np.array([]), y=np.array([]), height=np.array([]))
            self.err_lc.update()
            self.err_ph.update()

    def smooth_changed(self):
        if self.smooth.isChecked():
            self.flux_smoothed = bcsmooth(self.flux_ph, self.smooth_spin.value())
            self.curve_ph_smooth.setData(x=self.phase, y=self.flux_smoothed)
            self.curve_ph_smooth.update()
        else:
            self.curve_ph_smooth.setData(x=[], y=[])
            self.curve_ph_smooth.update()
    
    def invertyaxis_changed(self):
        if self.invertyaxis.isChecked():
            self.curve_lc.getViewBox().invertY(True)
            self.curve_ph.getViewBox().invertY(True)
            self.curve_lc.update()
            self.curve_ph.update()
        else:
            self.curve_lc.getViewBox().invertY(False)
            self.curve_ph.getViewBox().invertY(False)
            self.curve_lc.update()
            self.curve_ph.update()

    def hide_phase_changed(self):
        if self.hide_phase.isChecked():
            self.curve_ph.setData(x=[], y=[])
            self.curve_ph.update()
        else:
            self.curve_ph.setData(x=self.phase, y=self.flux_ph)
            self.curve_ph.update()

    def update_table(self):
        self.freqtm = TableModel()  # Create table model
        self.freqtm.update_tm(self.freq_cdf)
        # self.freqtv = self.freq_list
        self.freqtv.setModel(self.freqtm)
        # self.freqtv.horizontalHeader().setResizeMode(QtGui.QHeaderView.Stretch)
        # self.freqtv.resizeColumnsToContents()
        # self.freqtv.resizeRowsToContents()

    def show_table(self):
        new_cdf = pd.DataFrame({'Frequency': [np.round((1. / self.curr_per), 5)], 'Period': [np.round(self.per_u, 2)]})
        self.freq_cdf = new_cdf
        self.freqtm = TableModel()  # Create table model
        self.freqtm.update_tm(self.freq_cdf)
        # self.freqtv = self.freq_list
        self.freqtv.setModel(self.freqtm)
        # self.freqtv.horizontalHeader().setResizeMode(QtGui.QHeaderView.Stretch)
        # self.freqtv.resizeColumnsToContents()
        # self.freqtv.resizeRowsToContents()

    def onMouseClicked(self, point):
        self.clicked_point = point
        if self.clicked_point.button() == 1:
            # print(point)
            # tt = QtCore.QPointF(point.pos()[0], point.pos()[1])
            tt = self.current_point
            self.mouse_x = self.dft.plotItem.vb.mapSceneToView(tt).x()
            self.mouse_y = self.dft.plotItem.vb.mapSceneToView(tt).y()
            self.curr_per = 1. / self.mouse_x
            self.update_line()  # update vertical line
            self.phase_slider.setValue(499)  # reset phase shifter
            self.phase_spin.setValue(1. / self.curr_per)
            self.plot_ph()  # update phase plot
            self.error_changed()
            self.smooth_changed()
            self.hide_phase_changed()
            # self.ph.autoRange()
            self.lc.autoRange()
            self.nyq_and_per()

    def onMouseMoved(self, point):
        # freqa and freqb: to show size of window to find max peak
        self.current_point = point
        try:
            mousePoint_lc = self.lc.plotItem.vb.mapSceneToView(point)
            mousePoint_ph = self.ph.plotItem.vb.mapSceneToView(point)
            mousePoint_dft = self.dft.plotItem.vb.mapSceneToView(point)
            try:
                self.dft.removeItem(self.hover_curr_freq)
                self.dft.removeItem(self.hover_curr_freqa)
                self.dft.removeItem(self.hover_curr_freqb)
            except AttributeError:
                pass
            self.hover_curr_freq = pg.InfiniteLine(pos=mousePoint_dft.x(), pen=self.yelpen)
            try:
                xa = self.freq[np.where(np.abs(self.freq - mousePoint_dft.x()) < 0.001)[0][0]-self.size_to_find]
                xb = self.freq[np.where(np.abs(self.freq - mousePoint_dft.x()) < 0.001)[0][0]+self.size_to_find]
                self.hover_curr_freqa = pg.InfiniteLine(pos=xa, pen=self.yelpen)
                self.hover_curr_freqb = pg.InfiniteLine(pos=xb, pen=self.yelpen)
            except IndexError:
                pass

            self.dft.addItem(self.hover_curr_freq)
            try:
                self.dft.addItem(self.hover_curr_freqa)
                self.dft.addItem(self.hover_curr_freqb)
            except AttributeError:
                pass
            self.statusBar().showMessage(
                '{:2s}\tx: {:6.3f}   y: {:6.3f}\t{:>20s}\tx: {:6.3f}   y: {:6.3f}\t{:>20s}\tx: {:6.3f}   y: {:6.3f}'.format(
                    'LC: ', mousePoint_lc.x(), mousePoint_lc.y(), 'TRF: ', mousePoint_dft.x(), mousePoint_dft.y(), 'PHS: ',
                    mousePoint_ph.x(), mousePoint_ph.y()))
        except np.linalg.LinAlgError:
            pass


    def onClicked(self, index):     # When clicked on TreeView
        try:
            self.file_path = self.sender().model().filePath(index)
        except AttributeError:
            pass
        df_lc = pd.read_csv(self.file_path, delimiter="\s+", header=None)
        self.time, self.flux, self.ferr = df_lc[0].values, df_lc[1].values, df_lc[2].values
        # try:
        #     subprocess.check_output(['rm', temp_path+'lcf.trf'])
        # except subprocess.CalledProcessError:
        #     pass
        dft_process = subprocess.Popen(
            ['bash', self.dir_path + 'lcdft.sh', self.file_path, str(float(self.startf)), str(int(self.endf)),
             str(int(self.acc)), self.dir_path], stdout=subprocess.DEVNULL)
        self.dftprogress.setStyleSheet("QProgressBar::chunk:horizontal {background-color: #33A4DF;}")
        while True:
            if dft_process.poll() is None:
                self.recalcbutton.setText("CALCUALTING")
                try:
                    self.wc_process = int(subprocess.check_output(['wc', temp_path+'lcf.trf'], stderr=subprocess.STDOUT).split()[0].decode('utf-8'))
                    self.progress_bar()
                except subprocess.CalledProcessError:
                    pass
            else:
                self.recalcbutton.setText("ALMOST DONE")
                self.dftprogress.setValue(100)
                self.dftprogress.setStyleSheet("QProgressBar::chunk:horizontal {background-color: rgb(120, 240, 24);}")
                self.recalcbutton.setText("RECALCULATE")
                break
        
        df_dft = pd.read_csv(temp_path+'lcf.trf', delimiter="\s+", header=None)
        self.freq, self.ampl = df_dft[0].values, df_dft[1].values
        self.curr_per = 1. / self.freq[np.where(self.ampl == np.max(self.ampl[self.freq > 0.3]))[0][0]]
        self.curr_ampl = np.max(self.ampl[self.freq > 0.3])
        # self.sort_phases()
        self.nyq_and_per() # calc nyquist and show current period
        self.plot_lc()  # plot lc graph
        self.plot_dft()  # plot dft graph
        self.plot_ph()  # plot dft graph
        self.show_table()  # update frequency list
        self.update_line()
        self.error_changed()
        self.smooth_changed()
        self.hide_phase_changed()
        self.phase_slider.setValue(499)  # reset phase shifter
        self.smooth_spin.setValue(int(len(self.time) / 30))
        self.phase_spin.setValue(1. / self.curr_per)
        # self.ph.autoRange()
        self.lc.autoRange()
        self.check_freq()


    def populate(self):
        path = QtCore.QDir.currentPath()
        self.popmodel.setRootPath((QtCore.QDir.rootPath()))
        self.treeView.setModel(self.popmodel)
        self.treeView.setRootIndex(self.popmodel.index(path))
        # self.treeView.setSortingEnabled(True)
        for i in range(self.popmodel.columnCount()):
            self.treeView.hideColumn(i + 1)

    def plot_ph(self):
        if self.file_path != 'first_run':
            if self.time[0] < 0:
                self.time = self.time + self.time[0]*(-1)
            temp_phase = (np.fmod(self.time + self.shift_p, self.curr_per)) / self.curr_per
            self.phase = np.tile(temp_phase, self.nofphases) + np.repeat(np.arange(0, self.nofphases), len(temp_phase))
            self.sort_phases()
            self.curve_ph.setData(x=self.phase, y=self.flux_ph)
            self.curve_ph.getViewBox().setRange(yRange=self.curve_ph.dataBounds(1))
            # self.curve_ph.getViewBox().invertY(True)
            self.curve_ph.update()

    def plot_lc(self):
        if self.file_path != 'first_run':
            #print(self.file_path)
            self.curve_lc.setData(x=self.time, y=self.flux)
            # self.curve_lc.getViewBox().invertY(True)
            self.curve_lc.update()

    def update_line(self):  # plot when clicked
        try:
            self.dft.removeItem(self.line_curr_freq)
        except AttributeError:
            pass
        # self.line_curr_freq = pg.InfiniteLine(pos=1 / self.curr_per, pen=self.redpen, label=str(self.curr_ampl))
        self.line_curr_freq = pg.InfiniteLine(pos=1 / self.curr_per, pen=self.redpen)
        self.dft.addItem(self.line_curr_freq)

    def plot_dft(self):
        if self.file_path != 'first_run':
            self.curve_dft.setData(self.freq, self.ampl)
            # draw 4 and 5 S/N
            try:
                for snl in self.sn_lines:
                    self.dft.removeItem(snl)
            except AttributeError:
                pass
            self.sn_lines = []
            sn = np.mean(self.ampl)
            sn_four_line = pg.InfiniteLine(pos=4*sn, angle=0, pen=self.grelin, label="4 S/N", labelOpts={"position":0.95})
            sn_five_line = pg.InfiniteLine(pos=5*sn, angle=0, pen=self.grelin, label="5 S/N", labelOpts={"position":0.95})
            self.sn_lines.append(sn_four_line)
            self.sn_lines.append(sn_five_line)
            for snl in self.sn_lines:
                self.dft.addItem(snl)
            try:
                if self.hover_curr_freq.value() > self.endf:
                    self.hover_curr_freq.setValue(self.endf)
            except AttributeError:
                pass
            self.dft.autoRange()

    def closeEvent(self, event):
        msg_box = QtWidgets.QMessageBox()
        msg_box.setIcon(QtWidgets.QMessageBox.Information)
        msg_box.setText("Do you really want to quit?")
        msg_box.setWindowTitle("Exit?")
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
        return_value = msg_box.exec_()
        if return_value == QtWidgets.QMessageBox.Ok:
            print('[lcdft.py] Bye bye')
            event.accept()
        else:
            event.ignore()


if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon(dir_path + 'kzhya_ico-64.png'))

    # set stylesheet
    file = QtCore.QFile(dir_path + 'styles/light.qss')
    file.open(QtCore.QFile.ReadOnly | QtCore.QFile.Text)
    stream = QtCore.QTextStream(file)
    app.setStyleSheet(stream.readAll())
    app.setApplicationName('lcView')
    app.setFont(QtGui.QFont('Latin Modern Sans'))

    window = lcdftMain()
    window.move(0, 0)
    window.show()
    sys.exit(app.exec_())
