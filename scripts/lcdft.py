#!/usr/bin/env python3

import sys
from PyQt5 import QtCore, QtGui, uic, QtWidgets
import breeze_resources
import pyqtgraph as pg
import pandas as pd
import numpy as np
# from astropy import units as u
import os
from boxcar import smooth as bcsmooth
import subprocess

dir_path = os.path.realpath(__file__).replace(__file__.split('/')[-1], '')
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
        self.symredpen = (240, 24, 24)
        self.symbckpen = (24, 24, 24)
        self.sympen = (240, 240, 240)
        self.symgrepen = (24, 240, 24)
        self.symyelpen = (240, 240, 24)

        self.redpen = pg.mkPen(color=self.symredpen)
        self.bckpen = pg.mkPen(color=self.symbckpen)
        self.whipen = pg.mkPen(color=self.sympen)
        self.grepen = pg.mkPen(color=self.symgrepen)
        self.yelpen = pg.mkPen(color=self.symyelpen)

        # Initialize plots to connect with mouse
        self.ph.setBackground('#1C1717')
        self.lc.setBackground('#1C1717')
        self.dft.setBackground('#1C1717')

        self.curve_lc = self.lc.plot(x=[], y=[], pen=None, symbol='o', symbolSize=2.5, symbolPen=self.sympen,
                                     symbolBrush=self.sympen)
        self.err_lc = pg.ErrorBarItem(x=np.array([]), y=np.array([]), height=np.array([]), beam=0.0,
                                      pen={'color': 'w', 'width': 0.85})
        self.lc.addItem(self.err_lc)
        self.curve_ph = self.ph.plot(x=[], y=[], pen=None, symbol='o', symbolSize=2.5, symbolPen=self.sympen,
                                     symbolBrush=self.sympen)
        self.err_ph = pg.ErrorBarItem(x=np.array([]), y=np.array([]), height=np.array([]), beam=0.0,
                                      pen={'color': 'w', 'width': 0.85})
        self.ph.addItem(self.err_ph)
        self.curve_ph_smooth = self.ph.plot(x=[], y=[], pen=None, symbol='o', symbolSize=2.5, symbolPen=self.symgrepen,
                                            symbolBrush=self.symgrepen)
        self.curve_dft = self.dft.plot(x=[], y=[], pen=self.sympen)

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

        # Initialize variables
        self.shift_p = 0
        self.current_point = [0]  # sigMouseClicked and sigMouseMoved give different values (moved is correct)
        self.time, self.flux, self.ferr = [0, 0, 0]
        self.ferr_ph, self.flux_ph, self.flux_smoothed, self.phase = [0, 0, 0, 0]
        self.freq, self.ampl = [0, 0]
        self.nofphases = int(self.phase_dial.value())

        # Initialize variables for dft range
        self.startf = self.start_spin.value()
        self.endf = self.end_spin.value()
        self.acc = self.acc_spin.value()

        # ------------------------------ Graphics ----------------------------------- #
        self.file_path = 'first_run'  # path to recognize when first run
        self.max_per = 1.
        self.errors.stateChanged.connect(self.error_changed)
        self.smooth.stateChanged.connect(self.smooth_changed)
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
        self.ph.autoRange()

    def add_clicked(self):
        new_cdf = pd.DataFrame({'Frequency': [1. / self.curr_per], 'Period': [self.curr_per]}).round(5)
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
        self.phase_spin.setValue(float(item.data()))
        self.freq_to_remove = item

    def progress_bar(self):
        deltaT = np.ptp(self.time)
        self.max_progress = int((self.endf - self.startf) * self.acc * deltaT)
        self.dftprogress.setValue(int(self.wc_process / self.max_progress * 100))

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
        new_cdf = pd.DataFrame({'Frequency': [1. / self.curr_per], 'Period': [self.curr_per]}).round(5)
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
            self.ph.autoRange()
            self.lc.autoRange()

    def onMouseMoved(self, point):
        # print(point)
        self.current_point = point
        mousePoint_lc = self.lc.plotItem.vb.mapSceneToView(point)
        mousePoint_ph = self.ph.plotItem.vb.mapSceneToView(point)
        mousePoint_dft = self.dft.plotItem.vb.mapSceneToView(point)
        try:
            self.dft.removeItem(self.hover_curr_freq)
        except AttributeError:
            pass
        self.hover_curr_freq = pg.InfiniteLine(pos=mousePoint_dft.x(), pen=self.yelpen)
        self.dft.addItem(self.hover_curr_freq)
        self.statusBar().showMessage(
            '{:2s}\tx: {:6.3f}   y: {:6.3f}\t{:>20s}\tx: {:6.3f}   y: {:6.3f}\t{:>20s}\tx: {:6.3f}   y: {:6.3f}'.format(
                'LC: ', mousePoint_lc.x(), mousePoint_lc.y(), 'TRF: ', mousePoint_dft.x(), mousePoint_dft.y(), 'PHS: ',
                mousePoint_ph.x(), mousePoint_ph.y()))

    def onClicked(self, index):
        try:
            self.file_path = self.sender().model().filePath(index)
        except AttributeError:
            pass
        self.time, self.flux, self.ferr = np.loadtxt(self.file_path, unpack=True)
        try:
            subprocess.check_output(['rm', 'lcf.trf'])
        except subprocess.CalledProcessError:
            pass
        dft_process = subprocess.Popen(
            ['bash', self.dir_path + 'lcdft.bash', self.file_path, str(float(self.startf)), str(int(self.endf)),
             str(int(self.acc)), self.dir_path], stdout=subprocess.DEVNULL)
        self.dftprogress.setStyleSheet("QProgressBar::chunk:horizontal {background-color: #33A4DF;}")
        while True:
            if dft_process.poll() is None:
                try:
                    self.wc_process = int(
                        subprocess.check_output(['wc', 'lcf.trf'], stderr=subprocess.STDOUT).split()[0].decode('utf-8'))
                    self.progress_bar()
                except subprocess.CalledProcessError:
                    pass
            else:
                self.dftprogress.setValue(100)
                self.dftprogress.setStyleSheet("QProgressBar::chunk:horizontal {background-color: rgb(120, 240, 24);}")
                break

        self.freq, self.ampl = np.loadtxt('lcf.trf', unpack=True)
        self.curr_per = 1. / self.freq[np.where(self.ampl == np.max(self.ampl[self.freq > 0.3]))[0][0]]
        self.curr_ampl = np.max(self.ampl[self.freq > 0.3])
        # self.sort_phases()
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
        self.ph.autoRange()
        self.lc.autoRange()

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
            temp_phase = (np.fmod(self.time + self.shift_p, self.curr_per)) / self.curr_per
            self.phase = np.tile(temp_phase, self.nofphases) + np.repeat(np.arange(0, self.nofphases), len(temp_phase))
            self.sort_phases()
            self.curve_ph.setData(x=self.phase, y=self.flux_ph)
            self.curve_ph.update()

    def plot_lc(self):
        if self.file_path != 'first_run':
            self.curve_lc.setData(x=self.time, y=self.flux)
            self.curve_lc.getViewBox().invertY(True)
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
            print('Bye bye')
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

    window = lcdftMain()
    window.move(0, 0)
    window.show()
    sys.exit(app.exec_())
