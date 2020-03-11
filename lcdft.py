#!/usr/bin/env python3

import sys
from PyQt5 import QtCore, QtGui, uic, QtWidgets
import pyqtgraph as pg
import pandas as pd
import numpy as np
from astropy import units as u
from os import system
import os
from scripts.boxcar import smooth as bcsmooth

dir_path = os.path.realpath(__file__).replace(__file__.split('/')[-1], '')
qtCreatorFile = dir_path + "scripts/lcdft.ui"  # Enter file here.
Ui_MainWindow, QtBaseClass = uic.loadUiType(qtCreatorFile)


class lcdftMain(QtGui.QMainWindow, Ui_MainWindow):

    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        Ui_MainWindow.__init__(self)
        pg.setConfigOptions(antialias=True)

        self.setupUi(self)

        self.populate()
        self.treeView.clicked.connect(self.onClicked)

        self.dir_path = os.path.realpath(__file__).replace(__file__.split('/')[-1],
                                                           '')  # path to directory where app is opened
        self.time, self.flux, self.ferr = [0, 0, 0]
        self.flux_ph, self.flux_smoothed, self.phase = [0, 0, 0]
        self.freq, self.ampl = [0, 0]
        # --------------------------- Mouse position -------------------------------- #
        pen = pg.mkPen(color=(240, 240, 240))

        self.curve_lc = self.lc.plot(x=[], y=[], pen=pen)
        self.curve_ph = self.ph.plot(x=[], y=[], pen=pen)
        self.curve_dft = self.dft.plot(x=[], y=[], pen=pen)

        # Show positions of the mouse
        self.curve_lc.scene().sigMouseMoved.connect(self.onMouseMoved)
        self.curve_ph.scene().sigMouseMoved.connect(self.onMouseMoved)
        self.curve_dft.scene().sigMouseMoved.connect(self.onMouseMoved)

        # Get position from click
        self.mouse_x = 1.
        self.mouse_y = 1.
        self.per = 1. / self.mouse_x
        self.curve_dft.scene().sigMouseClicked.connect(self.onMouseClicked)
        # --------------------------------------------------------------------------- #

        # ------------------------------ Graphics ----------------------------------- #
        self.file_path = 'first_run'  # path to recognize when first run
        self.per = 1.  # starting per variable
        self.max_per = 1.
        self.plot_lc()  # plot lc graph
        self.plot_ph()  # plot lc graph
        self.plot_dft()  # plot dft graph
        self.errors.stateChanged.connect(self.state_changed)
        self.smooth.stateChanged.connect(self.state_changed)
        self.curve_dft.scene().sigMouseClicked.connect(self.state_changed)
        self.smooth_spin.valueChanged.connect(self.state_changed)
        self.phase_slider.valueChanged.connect(self.state_changed)
        # --------------------------------------------------------------------------- #

    def state_changed(self):
        self.per_n = self.per + float(self.phase_slider.value())*1e-12
        # print(self.per_n)
        self.phase = (self.time % self.per_n) / self.per_n
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

            self.lc.plot(self.time, self.flux, pen=None, symbol='o', symbolSize=2.5, symbolPen=(240, 240, 240),
                         symbolBrush=(240, 240, 240))
            self.ph.plot(self.phase, self.flux_ph, pen=None, symbol='o', symbolSize=2.5,
                         symbolPen=(240, 240, 240),
                         symbolBrush=(240, 240, 240))
            self.ph.plot(self.phase, self.flux_smoothed, pen=None, symbol='o', symbolSize=2.5,
                         symbolPen=(24, 240, 24),
                         symbolBrush=(24, 240, 24))
            self.lc.autoRange()
            self.ph.autoRange()

        elif self.errors.isChecked() is False and self.smooth.isChecked() is True:
            self.lc.clear()
            self.ph.clear()

            self.lc.plot(self.time, self.flux, pen=None, symbol='o', symbolSize=2.5, symbolPen=(240, 240, 240),
                         symbolBrush=(240, 240, 240))
            self.ph.plot(self.phase, self.flux_ph, pen=None, symbol='o', symbolSize=2.5,
                         symbolPen=(240, 240, 240),
                         symbolBrush=(240, 240, 240))
            self.ph.plot(self.phase, self.flux_smoothed, pen=None, symbol='o', symbolSize=2.5,
                         symbolPen=(24, 240, 24),
                         symbolBrush=(24, 240, 24))
            self.lc.autoRange()
            self.ph.autoRange()

        elif self.errors.isChecked() is True and self.smooth.isChecked() is False:
            self.lc.clear()
            self.ph.clear()

            self.lc.addItem(err_lc)
            self.ph.addItem(err_ph)

            self.lc.plot(self.time, self.flux, pen=None, symbol='o', symbolSize=2.5, symbolPen=(240, 240, 240),
                         symbolBrush=(240, 240, 240))
            self.ph.plot(self.phase, self.flux_ph, pen=None, symbol='o', symbolSize=2.5, symbolPen=(240, 240, 240),
                         symbolBrush=(240, 240, 240))
            self.lc.autoRange()
            self.ph.autoRange()

        elif self.errors.isChecked() is False and self.smooth.isChecked() is False:
            self.lc.clear()
            self.ph.clear()
            self.lc.plot(self.time, self.flux, pen=None, symbol='o', symbolSize=2.5, symbolPen=(240, 240, 240),
                         symbolBrush=(240, 240, 240))
            self.ph.plot(self.phase, self.flux_ph, pen=None, symbol='o', symbolSize=2.5, symbolPen=(240, 240, 240),
                         symbolBrush=(240, 240, 240))
            self.lc.autoRange()
            self.ph.autoRange()

    def onMouseClicked(self, point):
        if point.button() == 1:
            tt = QtCore.QPointF(point.pos()[0], point.pos()[1])
            self.mouse_x = self.dft.plotItem.vb.mapSceneToView(tt).x()
            self.mouse_y = self.dft.plotItem.vb.mapSceneToView(tt).y()
            self.per = 1. / self.mouse_x
            self.plot_ph()
            print(self.mouse_x, self.mouse_y)

    def onMouseMoved(self, point):
        mousePoint_lc = self.lc.plotItem.vb.mapSceneToView(point)
        mousePoint_ph = self.ph.plotItem.vb.mapSceneToView(point)
        mousePoint_dft = self.dft.plotItem.vb.mapSceneToView(point)
        self.statusBar().showMessage(
            '{:2s}\tx: {:6.3f}   y: {:6.3f}\t{:>20s}\tx: {:6.3f}   y: {:6.3f}\t{:>20s}\tx: {:6.3f}   y: {:6.3f}'.format(
                'LC: ', mousePoint_lc.x(), mousePoint_lc.y(), 'TRF: ', mousePoint_dft.x(), mousePoint_dft.y(), 'PHS: ',
                mousePoint_ph.x(), mousePoint_ph.y()))

    def onClicked(self, index):
        self.file_path = self.sender().model().filePath(index)
        self.time, self.flux, self.ferr = np.loadtxt(self.file_path, unpack=True)
        system('bash ' + self.dir_path + 'scripts/lcdft.bash ' + self.file_path + ' 0 300 ' + self.dir_path)
        self.freq, self.ampl = np.loadtxt('lcf.trf', unpack=True)
        self.plot_lc()  # plot lc graph
        self.plot_dft()  # plot dft graph
        self.plot_ph()  # plot dft graph
        self.state_changed()

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
            self.phase = (self.time % self.per) / self.per
            temp = zip(self.phase, self.flux)
            temp = sorted(temp)
            self.phase, self.flux_ph = zip(*temp)
            self.phase = np.array(self.phase)
            self.flux_ph = np.array(self.flux_ph)
            self.ph.clear()
            self.ph.plot(np.r_[self.phase, self.phase + 1], np.r_[self.flux_ph, self.flux_ph], pen=None, symbol='o',
                         symbolSize=2.5,
                         symbolPen=(240, 240, 240), symbolBrush=(240, 240, 240))
            self.ph.autoRange()

    def plot_lc(self):
        self.lc.setBackground('#1C1717')
        if self.file_path != 'first_run':
            self.lc.clear()
            self.lc.plot(self.time, self.flux, pen=None, symbol='o', symbolSize=2.5, symbolPen=(240, 240, 240),
                         symbolBrush=(240, 240, 240))
            self.lc.autoRange()

    def plot_dft(self):
        self.dft.setBackground('#1C1717')
        if self.file_path != 'first_run':
            pen = pg.mkPen(color=(240, 240, 240))
            self.per = 1. / self.freq[
                np.where(self.ampl == max(self.ampl[np.where(np.abs(self.freq - 0.5) <= 1e-6)[0][0]:]))[0][0]]
            self.max_per = self.per
            self.dft.clear()
            self.dft.plot(self.freq, self.ampl, pen=pen)
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
    # app.setWindowIcon(QtGui.QIcon('small-telescope-color-64.png'))
    app.setStyle('Fusion')
    window = lcdftMain()
    # window.setWindowFlags(QtCore.Qt.FramelessWindowHint)
    window.move(0, 0)
    window.show()
    sys.exit(app.exec_())
