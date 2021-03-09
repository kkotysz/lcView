#!/usr/bin/env python

from PyQt5 import QtCore, QtGui, uic, QtWidgets
import pyqtgraph as pg
import numpy as np
from itertools import combinations
import sys
import pandas as pd
import os

# dir_path = os.environ['HOME']+'/Dropbox/bin/'
dir_path = os.path.realpath(__file__).replace(__file__.split('/')[-1], '')
qtCreatorFile = dir_path + "pet.ui"  # Enter file here.


# Data for Petersen diagram
# data_path = os.environ['HOME']+'/Dropbox/data/'
data_path = dir_path + "data/"

hads = pd.read_csv(data_path+'hads_mmod2.dat', sep='\s+')
cep = pd.read_csv(data_path+'cep_mmod2.dat', sep='\s+')
rrl = pd.read_csv(data_path+'rrl_mmod2.dat', sep='\s+', comment= "#")
sxphe = pd.read_csv(data_path+'sxphe_mmod2.dat', sep='\s+')



Ui_MainWindow, QtBaseClass = uic.loadUiType(qtCreatorFile)

class petpoint:
    def __init__(self, ratio, pl, ps):
        self.ratio = ratio
        self.pl = pl
        self.ps = ps

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


class petMain(QtGui.QMainWindow, Ui_MainWindow):

    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        Ui_MainWindow.__init__(self)
        pg.setConfigOptions(antialias=True)
        #  self.showMaximized()
        self.setupUi(self)
        
        # Initialize pens
        self.symredpen = "#ff000d"
        self.symbckpen = (24, 24, 24)
        self.symwhipen = (240, 240, 240)
        self.symtrapen = (240, 240, 240, 0)
        self.symgrepen = "#76cd26"
        self.symyelpen = "#fffe7a"
        self.symblupen = "#047495"
        self.sympurpen = "#be03fd"
        self.sympurpleypen = "#8756e4"
        self.symhotmagentapen = "#f504c9"
        self.symorapen = "#dc4d01"
        self.symcoolgreenpen = "#33b864"
        self.symlightbluegreypen = "#b7c9e2"
        self.symforestgreenpen = "#06470c"

        self.redpen = pg.mkPen(color=self.symredpen, width=2.2)
        self.bckpen = pg.mkPen(color=self.symbckpen)
        self.whipen = pg.mkPen(color=self.symwhipen)
        self.grepen = pg.mkPen(color=self.symgrepen)
        self.grelin = pg.mkPen(color=self.symgrepen, style=QtCore.Qt.DotLine)
        self.yelpen = pg.mkPen(color=self.symyelpen, width=0.3)
        self.blupen = pg.mkPen(color=self.symblupen, width=0.3)
        self.trapen = pg.mkPen(color=self.symtrapen, width=0.3)
        
        self.pet.setBackground(self.bg_color)
        self.pet.setXRange(-1.6, 1, padding=0)
        self.pet.setYRange(0.4, 1, padding=0)
        self.pet.showGrid(x = True, y = True, alpha = 0.1)
        self.pet_legend = self.pet.addLegend(offset=(1, -70))
        self.pet.plotItem.setLabel('left', "shorter P / longer P")#, units='ppt/mmag')
        self.pet.plotItem.setLabel('bottom', "log(longer P)")#, units='1/d')
        # --------------------------- Mouse position -------------------------------- #
        # Show positions of the mouse
        self.pet.scene().sigMouseMoved.connect(self.onMouseMoved)
        # --------------------------------------------------------------------------- #
        
        self.hads.stateChanged.connect(lambda: self.pet_visibility("hads"))
        self.sxphe.stateChanged.connect(lambda: self.pet_visibility("sxphe"))
        self.cep.stateChanged.connect(lambda: self.pet_visibility("cep"))
        self.rrl.stateChanged.connect(lambda: self.pet_visibility("rrl"))
        
        self.curves_hads = self.plot_pet(hads, 'o', 6)
        self.curves_sxphe = self.plot_pet(sxphe, 'x', 8)
        self.curves_cep = self.plot_pet(cep, 't', 6)
        self.curves_rrl = self.plot_pet(rrl, 's', 6)
        
        self.legend_items = self.pet_legend.items[0:len(self.curves_hads)]
        self.pet_legend.clear()
        for it in self.legend_items[0:8]:
            self.pet_legend.addItem(it[0], it[1].text)
               
        self.read_freqs()
        self.create_freq() # Create layout with freqs from freq file
        self.populate_pet(self.freqs) # Create layout with freqs from freq file
        
    def show_on_pet(self):
        try:
            self.myr.setData(x=[], y=[])
            self.myr.update()
        except AttributeError:
            pass
        my_ratios = []
        my_pls = []
        for rcb, pp in zip(self.ratio_cb, self.petpoints):
            if rcb.isChecked():
                ratio = pp.ratio
                pl = pp.pl
                my_ratios.append(ratio)
                my_pls.append(pl)
        self.myr = self.pet.plot(x=np.log10(my_pls), y=my_ratios, pen=None, symbol='star', symbolSize=10, symbolPen=self.symwhipen, symbolBrush=self.symredpen)

    def addrem_freq(self, txt):
        print(txt)
        self.mask[int(txt)] ^= True
        # print(self.freqs[self.mask])
        self.populate_pet(self.freqs[self.mask])
        
    def read_freqs(self):
        try:
            if len(sys.argv) == 1:
                file_path = ''
            else:
                file_path = sys.argv[1]+"/"
                print(file_path)
            with open(file_path+'freq') as f:
            
                #wczytaj wszystkie linie
                lines = np.array(f.readlines())
                lines = np.array([line.strip("\n") for line in lines])
            
                #wczytaj norig, nall
                norig, nall = lines[0].split()
                norig = int(norig)
                nall = int(nall)
                self.n_combs = norig # number of combinations to calculate

                #wczytaj czestosci oryginalne
                self.freqs = np.array([line.strip() for line in lines if len(line.split())==1], dtype=float)
                for freq, i in zip(self.freqs[:self.n_combs], range(1,norig+1)):
                    print("# {0:2d} {1:12.6f}".format(i, freq))
            self.freq_exists = True
            self.mask = self.n_combs * [True]
        
         
        except FileNotFoundError:
            self.freq_exists = False
            print("[pet.py WARNING]: There is no freq file!")
            
    def populate_pet(self, freqs):
        if self.freq_exists:
            
            perms = np.asarray(list(combinations(freqs[:self.n_combs],2)))
            self.ratio_cb = []
            self.petpoints = []

            if self.ratio.layout() is None:
                self.ratio.setLayout(QtWidgets.QGridLayout())
            for i in reversed(range(self.ratio.layout().count())): 
                self.ratio.layout().itemAt(i).widget().setParent(None)

            #  print("{0:s}".format(50*'#'))
            #  print("#  {0:>8s} {1:<8s} {2:>8s} {3:<8s} {4:>8s}".format('f_la','P_sh','f_sm','P_lo','ratio'))
            for ii,n in zip(perms,range(len(perms))):
                i = ii[0]
                j = ii[1]
                i_idx = np.where(self.freqs == i)[0][0]+1
                j_idx = np.where(self.freqs == j)[0][0]+1

                if i/j > 1.:
                    self.rcb = QtWidgets.QCheckBox()
                    self.pp = petpoint(j/i, 1./i, 1./j)
                    self.rcb.setText("F"+str(j_idx)+"/F"+str(i_idx)+": {:.3f}  longer P: {:.3f} d".format(np.round(self.pp.ratio,3), np.round(self.pp.pl, 3)))
                    self.rcb.stateChanged.connect(self.show_on_pet)

                    self.ratio.layout().addWidget(self.rcb, n, 1)
                    self.ratio_cb.append(self.rcb)
                    self.petpoints.append(self.pp)
                    
                    #  print("10 {0:8.3f} {1:<8.3f} {2:8.3f} {3:<8.3f} {4:8.3f}".format(i, 1./i, j, 1./j, j/i))
                else:
                    self.rcb = QtWidgets.QCheckBox()
                    self.pp = petpoint(i/j, 1./j, 1./i)        
                    self.rcb.setText("F"+str(i_idx)+"/F"+str(j_idx)+": {:.3f}  longer P: {:.3f} d".format(np.round(self.pp.ratio,3), np.round(self.pp.pl, 3)))
                    self.rcb.stateChanged.connect(self.show_on_pet)

                    self.ratio.layout().addWidget(self.rcb, n, 1)
                    self.ratio_cb.append(self.rcb)
                    self.petpoints.append(self.pp)
                    
                    #  print("01 {0:8.3f} {1:<8.3f} {2:8.3f} {3:<8.3f} {4:8.3f}".format(j, 1./j, i, 1./i, i/j))
                    

    def create_freq(self):
            
        if self.freq_exists:

            self.freq_labels = []
            self.freq_cb = []
            self.toadd.setLayout(QtWidgets.QGridLayout())
            for i in range(self.n_combs):
                self.fl = QtWidgets.QLabel()
                self.fl.setText("{:2d}: Freq.: {:.3f} d\u207B¹".format(i+1, np.round(self.freqs[i], 3) ))
                self.fcb = QtWidgets.QCheckBox()
                self.fcb.setText("Period: {:.3f} d".format(np.round(1/self.freqs[i],3)))
                self.fcb.setChecked(True)
                
                self.toadd.layout().addWidget(self.fl, i, 0)
                self.toadd.layout().addWidget(self.fcb, i, 1)
                self.freq_labels.append(self.fl)
                self.freq_cb.append(self.fcb)
            
            for n, fcb in enumerate(self.freq_cb):
                fcb.stateChanged.connect(lambda _,i=n: self.addrem_freq(i))


    def plot_pet(self, pet_df, sym, syms):
        
        curves = []
        alph = 0.6
        
        fufo = pet_df.query('F > -1. and `1O` > -1.')
        curves.append(self.pet.plot(x=np.log10(fufo['F']), y=fufo['1O']/fufo['F'], pen=None, symbol=sym, symbolSize=syms, symbolPen=self.symgrepen,
                                     symbolBrush=self.symgrepen, name="1O/F"))
        fuso = pet_df.query('F > -1. and `2O` > -1.')
        curves.append(self.pet.plot(x=np.log10(fuso['F']), y=fuso['2O']/fuso['F'], pen=None, symbol=sym, symbolSize=syms, symbolPen=self.symyelpen,
                                     symbolBrush=self.symyelpen, name="2O/F"))
        futo = pet_df.query('F > -1. and `3O` > -1.')
        curves.append(self.pet.plot(x=np.log10(futo['F']), y=futo['3O']/futo['F'], pen=None, symbol=sym, symbolSize=syms, symbolPen=self.symblupen,
                                     symbolBrush=self.symblupen, name="3O/F"))
        fufoo = pet_df.query('F > -1. and `4O` > -1.')
        curves.append(self.pet.plot(x=np.log10(fufoo['F']), y=fufoo['4O']/fufoo['F'], pen=None, symbol=sym, symbolSize=syms, symbolPen=self.symcoolgreenpen,
                                     symbolBrush=self.symcoolgreenpen, name="X/F"))
        #  fufio = pet_df.query('F > -1. and `5O` > -1.')
        #  curves.append(self.pet.plot(x=np.log10(fufio['F']), y=fufio['5O']/fufio['F'], pen=None, symbol=sym, symbolSize=syms, symbolPen=self.symforestgreenpen,
                                     #  symbolBrush=self.symforestgreenpen, name="5O/F"))
        foso = pet_df.query('`1O` > -1. and `2O` > -1.')
        curves.append(self.pet.plot(x=np.log10(foso['1O']), y=foso['2O']/foso['1O'], pen=None, symbol=sym, symbolSize=syms, symbolPen=self.symredpen,
                                     symbolBrush=self.symredpen, name="2O/1O"))
        foto = pet_df.query('`1O` > -1. and `3O` > -1.')
        curves.append(self.pet.plot(x=np.log10(foto['1O']), y=foto['3O']/foto['1O'], pen=None, symbol=sym, symbolSize=syms, symbolPen=self.sympurpleypen,
                                     symbolBrush=self.sympurpleypen, name="3O/1O"))
        fofoo = pet_df.query('`1O` > -1. and `4O` > -1.')
        curves.append(self.pet.plot(x=np.log10(fofoo['1O']), y=fofoo['4O']/fofoo['1O'], pen=None, symbol=sym, symbolSize=syms, symbolPen=self.symlightbluegreypen,
                                     symbolBrush=self.symlightbluegreypen, name="X/1O"))
        fofio = pet_df.query('`1O` > -1. and `5O` > -1.')
        curves.append(self.pet.plot(x=np.log10(fofio['1O']), y=fofio['1O']/fofio['5O'], pen=None, symbol=sym, symbolSize=syms, symbolPen=self.sympurpen,
                                     symbolBrush=self.sympurpen, name="1O/X"))
        soto = pet_df.query('`2O` > -1. and `3O` > -1.')
        curves.append(self.pet.plot(x=np.log10(soto['2O']), y=soto['3O']/soto['2O'], pen=None, symbol=sym, symbolSize=syms, symbolPen=self.symorapen,
                                                    symbolBrush=self.symorapen, name="3O/2O"))
        #  print(fofio)
        #  print(fufoo)

        for curve in curves:
            curve.setAlpha(alph, False)                                     
        
        return curves

    def pet_visibility(self, ftype):
        if ftype == "hads":
            df = hads
            cb = self.hads
            sym = 'o'
            syms = 6
            curves = self.curves_hads
            #  self.legend_items = self.pet_legend.items[0:8]
        elif ftype == "sxphe":
            df = sxphe
            cb = self.sxphe
            sym = 'x'
            syms = 8
            curves = self.curves_sxphe
        elif ftype == "cep":
            df = cep
            cb = self.cep
            sym = 't'
            syms = 6
            curves = self.curves_cep
        elif ftype == "rrl":
            df = rrl
            cb = self.rrl
            sym = 's'
            syms = 6
            curves = self.curves_rrl
        
            
        if cb.checkState() == 0:
            for curve in curves:
                if ftype == "hads":
                    curve.setData(x=[], y=[])
                else:
                    self.pet.removeItem(curve)
        else:                   
            curves = self.plot_pet(df, sym, syms)
            self.pet_legend.clear()
            for it in self.legend_items:
                self.pet_legend.addItem(it[0], it[1].text)
            if ftype == "hads":
                self.curves_hads = curves
            elif ftype == "sxphe":
                self.curves_sxphe = curves
            elif ftype == "cep":
                self.curves_cep = curves
            elif ftype == "rrl":
                self.curves_rrl  = curves
            
    def onMouseMoved(self, point):
        # print(point)
        self.current_point = point
        mousePoint_pet = self.pet.plotItem.vb.mapSceneToView(point)
        self.statusBar().showMessage('{:2s}\tx: {:6.3f}   y: {:6.3f}'.format('PET: ', mousePoint_pet.x(), mousePoint_pet.y()))
                                    
    def closeEvent(self, event):
        msg_box = QtWidgets.QMessageBox()
        msg_box.setIcon(QtWidgets.QMessageBox.Information)
        msg_box.setText("Do you really want to quit?")
        msg_box.setWindowTitle("Exit?")
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
        if len(sys.argv) == 2:
            event.accept()
            exit()   
        return_value = msg_box.exec_()
        if return_value == QtWidgets.QMessageBox.Ok:
            print('Bye bye')
            event.accept()
        else:
            event.ignore()


if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    #  app.setWindowIcon(QtGui.QIcon(dir_path + 'kzhya_ico-64.png'))

    # set stylesheet
    #  file = QtCore.QFile(dir_path + 'styles/light.qss')
    #  file.open(QtCore.QFile.ReadOnly | QtCore.QFile.Text)
    #  stream = QtCore.QTextStream(file)
    #  app.setStyleSheet(stream.readAll())
    app.setApplicationName('pet')
    app.setFont(QtGui.QFont('Latin Modern Sans'))

    window = petMain()
    window.move(0, 0)
    window.show()
    sys.exit(app.exec_())

