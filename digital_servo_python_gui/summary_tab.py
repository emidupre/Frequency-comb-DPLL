from PyQt5 import QtCore, QtGui, QtWidgets, uic
import time
import sys
from datetime import datetime
import os
import inspect
import collections
import pathlib

import numpy as np
from functools import partial

from common import tictoc, getSNRcolorName, getPowerColorName, colorCoding

class SummaryTab(QtWidgets.QWidget):
    sig_reset_phase = QtCore.pyqtSignal(int)

    def __init__(self, channels_list=[1, 2, 3, 4], parent=None):
        super().__init__(parent)
        self.bDisplayTiming = False # set this to True to print profiling information
        self.channels_list = channels_list

        self.setupUI()

    def setupUI(self):
        uic.loadUi("summary_tab.ui", self)
        self.tab_visible = True

        # regroup all our per-channel widgets into an easily-accessible data structure:
        self.channel_widgets = dict()
        self.channels_list
        for widget_name in ["btnResetPhase", "lblPhase", "lblFreq", "lblSNR", "lblPower"]:
            d = dict()
            self.channel_widgets[widget_name] = d
            for channel_id in self.channels_list:
                widget = getattr(self, '%s%d' % (widget_name, channel_id))
                if widget_name.startswith('lbl'):
                    widget.setText('')
                self.channel_widgets[widget_name][channel_id] = widget

        # connect signals to slots:
        for channel_id in self.channel_widgets["btnResetPhase"]:
            reset_this_channel_func = partial(self.resetChannelPhase, channel_id)
            w = self.channel_widgets["btnResetPhase"][channel_id]
            w.clicked.connect(                     reset_this_channel_func)
            self.btnResetAllPhases.clicked.connect(reset_this_channel_func) # resetAllPhases will call these four slots

        # logging
        self._LOGGING_KEYS = ["phase1", "phase2", "phase3", "phase4", "freq1", "freq2", "freq3", "freq4", "snr1", "snr2", "snr3", "snr4", "power1", "power2", "power3", "power4"]
        self._logging_started = False
        self._logging_aggregate_data = collections.defaultdict(list)
        self._logging_path = None
        self._logging_timer = QtCore.QTimer(self)
        self._logging_timer.timeout.connect(self._logging_timer_event)
        self._logging_mutex = QtCore.QMutex()
        self.btnStartStopLogging.clicked.connect(self._logging_start_stop_clicked)
        self.txtLogStatus.setText("Stopped")
        colorCoding(self.txtLogStatus, "warning")

    def _logging_timer_event(self):
        if not self._logging_mutex.tryLock(250):
            return
        
        with open(self._logging_path, "a") as f:

            csv_data = []
            ts = datetime.now().isoformat()
            csv_data.append(ts)
            
            for k in self._LOGGING_KEYS:
                agg = self._logging_aggregate_data[k]
                n = len(agg)
                if n > 0:
                    csv_data.append("{:.6e}".format(float(np.min(agg)))),
                    csv_data.append("{:.6e}".format(float(np.max(agg)))),
                    csv_data.append("{:.6e}".format(float(np.mean(agg)))),
                    csv_data.append("{:.6e}".format(float(np.median(agg)))),
                else:
                    csv_data.append(""),
                    csv_data.append(""),
                    csv_data.append(""),
                    csv_data.append(""),
                csv_data.append(str(n)),
            
            f.write(",".join(csv_data))
            f.write("\n")
        
        self._logging_aggregate_data = collections.defaultdict(list)
        
        self._logging_mutex.unlock()
            
    def _logging_start_stop_clicked(self):
        if not self._logging_mutex.tryLock(250):
            return

        if self._logging_started:
            # stop logging
            pass
            self._logging_timer.stop()
            self.txtLogStatus.setText("Stopped")
            colorCoding(self.txtLogStatus, "warning")

            self._logging_started = False
        else:
            # start logging
            self._logging_aggregate_data = {k: [] for k in self._LOGGING_KEYS}
            self._logging_path = pathlib.Path(__file__).parent.joinpath("fnc_logging", datetime.now().strftime("%Y-%m-%dT%H-%M-%S_fnc_log")+".csv")
            self._logging_path.parent.mkdir(exist_ok=True, parents=True)

            self.txtLogPath.setText(str(self._logging_path))
            self.txtLogStatus.setText("Running")
            colorCoding(self.txtLogStatus, "ok")

            with open(self._logging_path, "w") as f:
                csv_data = ["iso_timestamp"]
                for k in self._LOGGING_KEYS:
                    csv_data.append("{}_min".format(k)),
                    csv_data.append("{}_max".format(k)),
                    csv_data.append("{}_mean".format(k)),
                    csv_data.append("{}_median".format(k)),
                    csv_data.append("{}_count".format(k)),
                f.write(",".join(csv_data))
                f.write("\n")

            self._logging_timer.start(5000)
            self._logging_started = True
            
        self._logging_mutex.unlock()

    def _logging_new_data(self, channel_id, quantity_name, value):
        if not self._logging_mutex.tryLock(250):
            return
        
        self._logging_aggregate_data[quantity_name+str(channel_id)].append(value)

        self._logging_mutex.unlock()


    def resetChannelPhase(self, channel_id):
        # print("resetChannelPhase(%d)" % (channel_id))
        self.sig_reset_phase.emit(channel_id)

    def setVisibility(self, bVisible):
        self.tab_visible = bVisible

    def newAmplitude(self, channel_id, mean_power_dBm, mean_amplitude):
        w = self.channel_widgets["lblPower"][channel_id]
        w.setText('% 05.1f dBm' % mean_power_dBm)
        colorCoding(w, getPowerColorName(mean_power_dBm))
        self._logging_new_data(channel_id, "power", mean_power_dBm)

    def newSNR(self, channel_id, filtered_baseband_snr, unfiltered_snr):
        w = self.channel_widgets["lblSNR"][channel_id]
        w.setText('%.1f dB' % filtered_baseband_snr)
        colorCoding(w, getSNRcolorName(filtered_baseband_snr))
        self._logging_new_data(channel_id, "snr", filtered_baseband_snr)

    def newFreqData(self, channel_id, freq_Hz):
        w = self.channel_widgets["lblFreq"][channel_id]
        w.setText('% .6f Hz' % freq_Hz)
        self._logging_new_data(channel_id, "freq", freq_Hz)

    def newPhasePoint(self, phase_data):
        if phase_data is None:
            return
        if not self.tab_visible:
            return
        for channel_id in self.channels_list:
            self._newPhaseSingleChannel(self.channel_widgets["lblPhase"][channel_id], phase_data[channel_id])
            self._logging_new_data(channel_id, "phase", phase_data[channel_id])

    def _newPhaseSingleChannel(self, widget, phi):
        widget.setText('%.6f cycles' % phi)

        if abs(phi) < 0.1: # these are pretty arbitrary at the moment, would be better if this would be configurable
            color_name = 'ok'
        elif abs(phi) < 0.5:
            color_name = 'warning'
        else:
            color_name = 'bad'
        colorCoding(widget, color_name)

class TestWidget(QtWidgets.QWidget):
    """ Used as a top-level widget when testing """
    def __init__(self, gui_test, parent=None):
        super().__init__(parent)
        self.gui_test = gui_test

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.timerEvent)
        self.timer.start(1000)

    def timerEvent(self):
        """ Simulate signals coming from test.py and channel_gui.py """
        phase_data = dict()
        for channel_id in [1, 2, 3, 4]:
            self.gui_test.newAmplitude(channel_id, -10 - channel_id, 0.1*channel_id)
            self.gui_test.newSNR(channel_id, filtered_baseband_snr = 30 + channel_id)
            self.gui_test.newFreqData(channel_id, freq_Hz=10e6+1e6*channel_id)
            phase_data[channel_id] = channel_id + 0.01*np.random.randn(1)
        self.gui_test.newPhasePoint(phase_data)

def main():
    # for testing when ran without a parent GUI
    app = QtWidgets.QApplication(sys.argv)
    GUI = SummaryTab()
    GUI.show()

    test_widget = TestWidget(GUI)


    
    app.exec_()

if __name__ == '__main__':
    main()

