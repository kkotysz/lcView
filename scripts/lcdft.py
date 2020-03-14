#!/usr/bin/env python3

import sys
from PyQt5 import QtCore, QtGui, uic, QtWidgets
import pyqtgraph as pg
import pandas as pd
import numpy as np
# from astropy import units as u
from os import system
import os
from boxcar import smooth as bcsmooth

dir_path = os.path.realpath(__file__).replace(__file__.split('/')[-1], '')
qtCreatorFile = dir_path + "lcdft.ui"  # Enter file here.
Ui_MainWindow, QtBaseClass = uic.loadUiType(qtCreatorFile)


class TextScrollBarStyle(QtGui.QProxyStyle):
    def drawComplexControl(self, control, option, painter, widget):
        # call the base implementation which will draw anything Qt will ask
        super().drawComplexControl(control, option, painter, widget)
        # check if control type and orientation match
        if control == QtGui.QStyle.CC_ScrollBar and option.orientation == QtCore.Qt.Horizontal:
            # the option is already provided by the widget's internal paintEvent;
            # from this point on, it's almost the same as explained above, but
            # setting the pen might be required for some styles
            painter.setPen(widget.palette().color(QtGui.QPalette.WindowText))
            margin = self.frameMargin(widget) + 1

            sliderRect = self.subControlRect(control, option,
                                             QtGui.QStyle.SC_ScrollBarSlider, widget)
            painter.drawText(sliderRect, QtCore.Qt.AlignCenter, widget.sliderText)

            subPageRect = self.subControlRect(control, option,
                                              QtGui.QStyle.SC_ScrollBarSubPage, widget)
            subPageRect.setRight(sliderRect.left() - 1)
            painter.save()
            painter.setClipRect(subPageRect)
            painter.drawText(subPageRect.adjusted(margin, 0, 0, 0),
                             QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, widget.preText)
            painter.restore()

            addPageRect = self.subControlRect(control, option,
                                              QtGui.QStyle.SC_ScrollBarAddPage, widget)
            addPageRect.setLeft(sliderRect.right() + 1)
            painter.save()
            painter.setClipRect(addPageRect)
            painter.drawText(addPageRect.adjusted(0, 0, -margin, 0),
                             QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, widget.postText)
            painter.restore()

    def frameMargin(self, widget):
        # a helper function to get the default frame margin which is usually added
        # to widgets and sub widgets that might look like a frame, which usually
        # includes the slider of a scrollbar
        option = QtGui.QStyleOptionFrame()
        option.initFrom(widget)
        return self.pixelMetric(QtGui.QStyle.PM_DefaultFrameWidth, option, widget)

    def subControlRect(self, control, option, subControl, widget):
        rect = super().subControlRect(control, option, subControl, widget)
        if (control == QtGui.QStyle.CC_ScrollBar
                and isinstance(widget, StyledTextScrollBar)
                and option.orientation == QtCore.Qt.Horizontal):
            if subControl == QtGui.QStyle.SC_ScrollBarSlider:
                # get the *default* groove rectangle (the space in which the
                # slider can move)
                grooveRect = super().subControlRect(control, option,
                                                    QtGui.QStyle.SC_ScrollBarGroove, widget)
                # ensure that the slider is wide enough for its text
                width = max(rect.width(),
                            widget.sliderWidth + self.frameMargin(widget))
                # compute the position of the slider according to the
                # scrollbar value and available space (the "groove")
                pos = self.sliderPositionFromValue(widget.minimum(),
                                                   widget.maximum(), widget.sliderPosition(),
                                                   grooveRect.width() - width)
                # return the new rectangle
                return QtCore.QRect(grooveRect.x() + pos,
                                    (grooveRect.height() - rect.height()) / 2,
                                    width, rect.height())
            elif subControl == QtGui.QStyle.SC_ScrollBarSubPage:
                # adjust the rectangle based on the slider
                sliderRect = self.subControlRect(
                    control, option, QtGui.QStyle.SC_ScrollBarSlider, widget)
                rect.setRight(sliderRect.left())
            elif subControl == QtGui.QStyle.SC_ScrollBarAddPage:
                # same as above
                sliderRect = self.subControlRect(
                    control, option, QtGui.QStyle.SC_ScrollBarSlider, widget)
                rect.setLeft(sliderRect.right())
        return rect

    def hitTestComplexControl(self, control, option, pos, widget):
        if control == QtGui.QStyle.CC_ScrollBar:
            # check click events against the resized slider
            sliderRect = self.subControlRect(control, option,
                                             QtGui.QStyle.SC_ScrollBarSlider, widget)
            if pos in sliderRect:
                return QtGui.QStyle.SC_ScrollBarSlider
        return super().hitTestComplexControl(control, option, pos, widget)


class StyledTextScrollBar(QtWidgets.QScrollBar):
    def __init__(self, sliderText='', preText='', postText=''):
        super().__init__(QtCore.Qt.Orientation.Horizontal)
        self.setStyle(TextScrollBarStyle())
        self.preText = preText
        self.postText = postText
        self.sliderText = sliderText
        self.sliderTextMargin = 2
        self.sliderWidth = self.fontMetrics().width(sliderText) + self.sliderTextMargin + 2

    def setPreText(self, text):
        self.preText = text
        self.update()

    def setPostText(self, text):
        self.postText = text
        self.update

    def setSliderText(self, text):
        self.sliderText = text
        self.sliderWidth = self.fontMetrics().width(text) + self.sliderTextMargin + 2

    def setSliderTextMargin(self, margin):
        self.sliderTextMargin = margin
        self.sliderWidth = self.fontMetrics().width(self.sliderText) + margin + 2

    def sizeHint(self):
        # give the scrollbar enough height for the font
        hint = super().sizeHint()
        if hint.height() < self.fontMetrics().height() + 4:
            hint.setHeight(self.fontMetrics().height() + 4)
        return hint


class TableModel(QtCore.QAbstractTableModel):
    def __init__(self):
        super(TableModel, self).__init__()
        self.datatable = None
        self.colLabels = None

    def update(self, datain):
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

        self.populate()
        self.treeView.clicked.connect(self.onClicked)

        self.dir_path = os.path.realpath(__file__).replace(__file__.split('/')[-1],
                                                           '')  # path to directory where app is opened
        # Initialize pens
        self.symredpen = (240, 24, 24)
        self.symbckpen = (24, 24, 24)
        self.sympen = (240, 240, 240)
        self.symgrepen = (24, 240, 24)

        self.redpen = pg.mkPen(color=self.symredpen)
        self.bckpen = pg.mkPen(color=self.symbckpen)
        self.whipen = pg.mkPen(color=self.sympen)
        self.grepen = pg.mkPen(color=self.symgrepen)

        # Initialize variables
        # self.shift_p = float(self.phase_shifter.value())
        self.current_point = [
            0]  # needed, because sigMouseClicked and sigMouseMoved give slighlty different values (moved is correct)
        self.time, self.flux, self.ferr = [0, 0, 0]
        self.flux_ph, self.flux_smoothed, self.phase = [0, 0, 0]
        self.freq, self.ampl = [0, 0]
        # --------------------------- Mouse position -------------------------------- #

        # Initialize plots to connect with mouse
        self.curve_lc = self.lc.plot(x=[], y=[], pen=self.bckpen)
        self.curve_ph = self.ph.plot(x=[], y=[], pen=self.bckpen)
        self.curve_dft = self.dft.plot(x=[], y=[], pen=self.bckpen)

        # Show positions of the mouse
        self.curve_lc.scene().sigMouseMoved.connect(self.onMouseMoved)
        self.curve_ph.scene().sigMouseMoved.connect(self.onMouseMoved)
        self.curve_dft.scene().sigMouseMoved.connect(self.onMouseMoved)

        # Get position from click
        self.mouse_x = 1.
        self.mouse_y = 1.
        self.curr_per = 1. / self.mouse_x
        self.curr_per_n = 1. / self.mouse_x
        self.curr_ampl = 1. / self.mouse_y
        self.curve_dft.scene().sigMouseClicked.connect(self.onMouseClicked)

        # Initialize variables for dft range
        self.startf = self.start_spin.value()
        self.endf = self.end_spin.value()
        self.acc = self.acc_spin.value()
        # --------------------------------------------------------------------------- #

        # ------------------------------ Phase Shifter------------------------------- #
        self.phase_shifter = StyledTextScrollBar()
        self.phaselayout.addWidget(self.phase_shifter)
        self.phase_shifter.setSliderText('PHASE SHIFTER')
        self.phase_shifter.setValue(49)
        self.phase_shifter.valueChanged.connect(lambda: self.state_changed(phase_flag=True))
        # --------------------------------------------------------------------------- #

        # --------------------------------------------------------------------------- #
        # ------------------------------ Graphics ----------------------------------- #
        self.file_path = 'first_run'  # path to recognize when first run
        self.max_per = 1.
        self.plot_lc()  # plot lc graph
        self.plot_ph()  # plot lc graph
        self.plot_dft()  # plot dft graph
        self.errors.stateChanged.connect(lambda: self.state_changed(click_flag=True))
        self.smooth.stateChanged.connect(lambda: self.state_changed(click_flag=True))
        self.curve_dft.scene().sigMouseClicked.connect(lambda: self.state_changed(click_flag=True))
        self.smooth_spin.valueChanged.connect(lambda: self.state_changed())
        self.freq_slider.valueChanged.connect(lambda: self.state_changed())
        self.start_spin.valueChanged.connect(self.getdftrange)
        self.end_spin.valueChanged.connect(self.getdftrange)
        self.acc_spin.valueChanged.connect(self.getdftrange)
        self.recalc.clicked.connect(self.onClicked)
        # --------------------------------------------------------------------------- #

        # -------------------- Start table with frequency data ---------------------- #
        #                                                                             #
        freq_cdf = df = pd.DataFrame(data={'Frequency': [], 'Period': []})  # Create table data
        # freq_cdf = df = pd.DataFrame(data={'Frequency': [], 'Period': [], 'Amplitude': []})  # Create table data
        self._freqtm = TableModel()  # Create table model
        self._freqtm.update(freq_cdf)
        self._freqtv = self.freq_list
        self._freqtv.setModel(self._freqtm)
        self._freqtv.horizontalHeader().setResizeMode(QtGui.QHeaderView.Stretch)
        # self._freqtv.resizeColumnsToContents()
        # self._freqtv.resizeRowsToContents()
        #                                                                             #
        # --------------------------------------------------------------------------- #

    def getdftrange(self):
        self.startf = self.start_spin.value()
        self.endf = self.end_spin.value()
        self.acc = self.acc_spin.value()

    def state_changed(self, click_flag=False, phase_flag=False):  # click_flag to know if is executed by sigMouseClick
        if click_flag is False:
            deltaT = self.time[-1] - self.time[0]
            self.curr_per_n = 1. / (1. / self.curr_per + float(self.freq_slider.value()) * 0.01 / deltaT)
            self.update_line()  # update vertical line with current slider
            self.show_table()  # update table values with slider
        self.shift_p = (float(self.phase_shifter.value()) - 50.) / 100. * self.curr_per_n
        self.phase = ((self.time + self.shift_p) % self.curr_per_n) / self.curr_per_n
        try:
            temp = zip(self.phase, self.flux)
            temp = sorted(temp)
            self.phase, self.flux_ph = zip(*temp)
            self.phase = np.array(self.phase)
            self.flux_ph = np.array(self.flux_ph)
            self.flux_smoothed = bcsmooth(self.flux_ph, self.smooth_spin.value())

            err_lc = pg.ErrorBarItem(x=self.time, y=self.flux, height=self.ferr, beam=0.0,
                                     pen={'color': 'w', 'width': 0})
            err_ph = pg.ErrorBarItem(x=self.phase, y=self.flux_ph, height=self.ferr, beam=0.0,
                                     pen={'color': 'w', 'width': 0})

            if self.errors.isChecked() is True and self.smooth.isChecked() is True:
                self.lc.clear()
                self.ph.clear()

                self.lc.addItem(err_lc)
                self.ph.addItem(err_ph)

                self.lc.plot(self.time, self.flux, pen=None, symbol='o', symbolSize=2.5, symbolPen=self.sympen,
                             symbolBrush=self.sympen)
                self.ph.plot(self.phase, self.flux_ph, pen=None, symbol='o', symbolSize=2.5,
                             symbolPen=self.sympen,
                             symbolBrush=self.sympen)
                self.ph.plot(self.phase, self.flux_smoothed, pen=None, symbol='o', symbolSize=2.5,
                             symbolPen=self.symgrepen,
                             symbolBrush=self.symgrepen)
                self.lc.autoRange()
                if phase_flag is False:
                    self.ph.autoRange()

            elif self.errors.isChecked() is False and self.smooth.isChecked() is True:
                self.lc.clear()
                self.ph.clear()

                self.lc.plot(self.time, self.flux, pen=None, symbol='o', symbolSize=2.5, symbolPen=self.sympen,
                             symbolBrush=self.sympen)
                self.ph.plot(self.phase, self.flux_ph, pen=None, symbol='o', symbolSize=2.5,
                             symbolPen=self.sympen,
                             symbolBrush=self.sympen)
                self.ph.plot(self.phase, self.flux_smoothed, pen=None, symbol='o', symbolSize=2.5,
                             symbolPen=self.symgrepen,
                             symbolBrush=self.symgrepen)
                self.lc.autoRange()
                if phase_flag is False:
                    self.ph.autoRange()

            elif self.errors.isChecked() is True and self.smooth.isChecked() is False:
                self.lc.clear()
                self.ph.clear()

                self.lc.addItem(err_lc)
                self.ph.addItem(err_ph)

                self.lc.plot(self.time, self.flux, pen=None, symbol='o', symbolSize=2.5, symbolPen=self.sympen,
                             symbolBrush=self.sympen)
                self.ph.plot(self.phase, self.flux_ph, pen=None, symbol='o', symbolSize=2.5, symbolPen=self.sympen,
                             symbolBrush=self.sympen)
                self.lc.autoRange()
                if phase_flag is False:
                    self.ph.autoRange()

            elif self.errors.isChecked() is False and self.smooth.isChecked() is False:
                self.lc.clear()
                self.ph.clear()
                self.lc.plot(self.time, self.flux, pen=None, symbol='o', symbolSize=2.5, symbolPen=self.sympen,
                             symbolBrush=self.sympen)
                self.ph.plot(self.phase, self.flux_ph, pen=None, symbol='o', symbolSize=2.5, symbolPen=self.sympen,
                             symbolBrush=self.sympen)
                self.lc.autoRange()
                if phase_flag is False:
                    self.ph.autoRange()
        except TypeError:
            print("ERROR: Probably file is not loaded.")

    def show_table(self):
        freq_cdf = df = pd.DataFrame(
            data={'Frequency': [1. / self.curr_per_n], 'Period': [self.curr_per_n]}).round(
            5)  # Create table data
        # freq_cdf = df = pd.DataFrame(
        #     data={'Frequency': [1./self.curr_per], 'Period': [self.curr_per], 'Amplitude': [self.curr_ampl]}).round(
        #     3)  # Create table data
        self._freqtm = TableModel()  # Create table model
        self._freqtm.update(freq_cdf)
        self._freqtv = self.freq_list
        self._freqtv.setModel(self._freqtm)
        self._freqtv.horizontalHeader().setResizeMode(QtGui.QHeaderView.Stretch)
        # self._freqtv.resizeColumnsToContents()
        # self._freqtv.resizeRowsToContents()

    def onMouseClicked(self, point):
        if point.button() == 1:
            # print(point)
            # tt = QtCore.QPointF(point.pos()[0], point.pos()[1])
            tt = self.current_point
            self.mouse_x = self.dft.plotItem.vb.mapSceneToView(tt).x()
            self.mouse_y = self.dft.plotItem.vb.mapSceneToView(tt).y()
            self.curr_per = 1. / self.mouse_x
            self.curr_per_n = self.curr_per
            self.plot_ph()  # update phase plot
            self.show_table()  # update frequency list
            self.plot_line()  # plot vertical line
            self.freq_slider.setValue(0)  # reset slider
            self.phase_shifter.setValue(50)  # reset phase shifter

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
        self.hover_curr_freq = pg.InfiniteLine(pos=mousePoint_dft.x(), pen=self.whipen)
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
        system('bash ' + self.dir_path + 'lcdft.bash ' + self.file_path + ' ' + str(int(self.startf)) + ' ' + str(int(
            self.endf)) + ' ' + str(int(self.acc)) + ' ' + self.dir_path)
        self.freq, self.ampl = np.loadtxt('lcf.trf', unpack=True)
        self.smooth_spin.setValue(int(len(self.time) / 10))
        self.plot_lc()  # plot lc graph
        self.plot_dft()  # plot dft graph
        self.plot_ph()  # plot dft graph
        self.show_table()  # update frequency list
        self.state_changed()
        self.freq_slider.setValue(0)  # reset slider
        self.phase_shifter.setValue(50)  # reset phase shifter

    def populate(self):
        path = QtCore.QDir.currentPath()
        self.model = QtWidgets.QFileSystemModel()
        self.model.setRootPath((QtCore.QDir.rootPath()))
        self.treeView.setModel(self.model)
        self.treeView.setRootIndex(self.model.index(path))
        # self.treeView.setSortingEnabled(True)
        for i in range(self.model.columnCount()):
            self.treeView.hideColumn(i + 1)

    def plot_ph(self):
        self.ph.setBackground('#1C1717')
        if self.file_path != 'first_run':
            self.phase = (self.time % self.curr_per) / self.curr_per
            temp = zip(self.phase, self.flux)
            temp = sorted(temp)
            self.phase, self.flux_ph = zip(*temp)
            self.phase = np.array(self.phase)
            self.flux_ph = np.array(self.flux_ph)
            self.ph.clear()
            self.ph.plot(np.r_[self.phase, self.phase + 1], np.r_[self.flux_ph, self.flux_ph], pen=None, symbol='o',
                         symbolSize=2.5,
                         symbolPen=self.sympen, symbolBrush=self.sympen)
            self.ph.autoRange()

    def plot_lc(self):
        self.lc.setBackground('#1C1717')
        if self.file_path != 'first_run':
            self.lc.clear()
            self.lc.plot(self.time, self.flux, pen=None, symbol='o', symbolSize=2.5, symbolPen=self.sympen,
                         symbolBrush=self.sympen)
            self.lc.autoRange()

    def update_line(self):
        try:
            self.dft.removeItem(self.line_curr_freq)
        except AttributeError:
            pass
        self.line_curr_freq = pg.InfiniteLine(pos=1. / self.curr_per_n, pen=self.redpen)
        self.dft.addItem(self.line_curr_freq)

    def plot_line(self):
        try:
            self.dft.removeItem(self.line_curr_freq)
        except AttributeError:
            pass
        self.line_curr_freq = pg.InfiniteLine(pos=self.mouse_x, pen=self.redpen)
        self.dft.addItem(self.line_curr_freq)

    def plot_dft(self):
        self.dft.setBackground('#1C1717')
        if self.file_path != 'first_run':
            self.curr_per_n = 1. / self.freq[np.where(self.ampl == max(self.ampl[self.freq > 0.3]))[0][0]]
            self.curr_per = self.curr_per_n
            self.curr_ampl = max(self.ampl[self.freq > 0.3])
            self.max_per = self.curr_per
            self.dft.clear()
            self.dft.plot(self.freq, self.ampl, pen=self.sympen)
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
    app.setStyle('Breeze')
    app.setApplicationName('lcView')
    window = lcdftMain()
    window.move(0, 0)
    window.show()
    sys.exit(app.exec_())
