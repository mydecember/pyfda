# -*- coding: utf-8 -*-
#
# This file is part of the pyFDA project hosted at https://github.com/chipmuenk/pyfda
#
# Copyright © pyFDA Project Contributors
# Licensed under the terms of the MIT License
# (see file LICENSE in root directory for details)

"""
Widget for plotting impulse and general transient responses
"""
import logging
logger = logging.getLogger(__name__)

from ..compat import QWidget, pyqtSignal, QTabWidget, QVBoxLayout

import numpy as np
from numpy import pi, sin, cos, sqrt
import scipy.signal as sig
import matplotlib.patches as mpl_patches

import pyfda.filterbroker as fb
import pyfda.pyfda_fix_lib as fx
from pyfda.pyfda_lib import expand_lim, to_html, safe_eval, pprint_log
from pyfda.pyfda_qt_lib import qget_cmb_box, qset_cmb_box, qstyle_widget
from pyfda.pyfda_rc import params # FMT string for QLineEdit fields, e.g. '{:.3g}'
from pyfda.plot_widgets.mpl_widget import MplWidget, stems, no_plot
#from mpl_toolkits.mplot3d.axes3d import Axes3D
from .plot_impz_ui import PlotImpz_UI

# TODO: "Home" calls redraw for botb mpl widgets
# TODO: changing the view on some widgets redraws h[n] unncessarily
# TODO: keywords 'ms', 'alpha', 'lw' not defined for stems?
# TODO: ui for phases

classes = {'Plot_Impz':'h[n]'} #: Dict containing class name : display name

class Plot_Impz(QWidget):
    """
    Construct a widget for plotting impulse and general transient responses
    """
    # incoming
    sig_rx = pyqtSignal(object)
    # outgoing, e.g. when stimulus has been calculated
    sig_tx = pyqtSignal(object)


    def __init__(self, parent):
        super(Plot_Impz, self).__init__(parent)

        self.ACTIVE_3D = False
        self.ui = PlotImpz_UI(self) # create the UI part with buttons etc.

        # initial settings
        self.needs_draw = True   # flag whether plots need to be updated 
        self.needs_redraw = [True] * 2 # flag which plot needs to be redrawn
        self.fx_sim = False # initial setting for fixpoint simulation
        self.tool_tip = "Impulse and transient response"
        self.tab_label = "h[n]"
        self.active_tab = 0 # index for active tab
        
        self.fxqc_dict = fb.fil[0]['fxqc'] # dict with fixpoint infos
        
        self.fmt_plot_resp = {'color':'red', 'linewidth':2, 'alpha':0.5}
        self.fmt_mkr_resp = {'color':'red', 'alpha':0.5}        
        self.fmt_plot_stim = {'color':'blue', 'linewidth':2, 'alpha':0.5}
        self.fmt_mkr_stim = {'color':'blue', 'alpha':0.5}
        self.fmt_plot_stmq = {'color':'darkgreen', 'linewidth':2, 'alpha':0.5}
        self.fmt_mkr_stmq = {'color':'darkgreen', 'alpha':0.5}

        self.fmt_stem_stim = params['mpl_stimuli']


        self._construct_UI()

        #--------------------------------------------
        # initialize routines and settings
        self._log_mode_time()
        self._log_mode_freq()
        self.fx_select()    # initialize fixpoint or float simulation    
        self.impz() # initial calculation of stimulus and response and drawing


    def _construct_UI(self):
        """
        Create the top level UI of the widget, consisting of matplotlib widget
        and control frame.
        """
        #----------------------------------------------------------------------
        # Define MplWidget for TIME domain plots
        #----------------------------------------------------------------------
        self.mplwidget_t = MplWidget(self)
        self.mplwidget_t.setObjectName("mplwidget_t1")
        self.mplwidget_t.layVMainMpl.addWidget(self.ui.wdg_ctrl_time)
        self.mplwidget_t.layVMainMpl.setContentsMargins(*params['wdg_margins'])
        #----------------------------------------------------------------------
        # Define MplWidget for FREQUENCY domain plots
        #----------------------------------------------------------------------
        self.mplwidget_f = MplWidget(self)
        self.mplwidget_f.setObjectName("mplwidget_f1")
        self.mplwidget_f.layVMainMpl.addWidget(self.ui.wdg_ctrl_freq)
        self.mplwidget_f.layVMainMpl.setContentsMargins(*params['wdg_margins'])

        #----------------------------------------------------------------------
        # Tabbed layout with vertical tabs
        #----------------------------------------------------------------------
        self.tabWidget = QTabWidget(self)
        self.tabWidget.addTab(self.mplwidget_t, "Time")
        self.tabWidget.addTab(self.mplwidget_f, "Frequency")
        # list with tabWidgets
        self.tab_mplwidgets = ["mplwidget_t", "mplwidget_f"]
        self.tabWidget.setTabPosition(QTabWidget.West)

        layVMain = QVBoxLayout()
        layVMain.addWidget(self.tabWidget)
        layVMain.addWidget(self.ui.wdg_ctrl_stim)
        layVMain.addWidget(self.ui.wdg_ctrl_run)
        layVMain.setContentsMargins(*params['wdg_margins'])#(left, top, right, bottom)

        self.setLayout(layVMain)
        #----------------------------------------------------------------------
        # SIGNALS & SLOTs
        #----------------------------------------------------------------------
        # --- run control ---
        self.ui.cmb_sim_select.currentIndexChanged.connect(self.fx_select)
        self.ui.but_run.clicked.connect(self.fx_run)
        self.ui.chk_fx_scale.clicked.connect(self.draw_impz)

        # --- time domain plotting ---
        self.ui.cmb_plt_time_resp.currentIndexChanged.connect(self.draw_impz)
        self.ui.cmb_plt_time_stim.currentIndexChanged.connect(self.draw_impz)
        self.ui.chk_stim_bl.clicked.connect(self.draw_impz)        
        self.ui.cmb_plt_time_stmq.currentIndexChanged.connect(self.draw_impz)        
        self.ui.chk_log_time.clicked.connect(self._log_mode_time)
        self.ui.led_log_bottom_time.editingFinished.connect(self._log_mode_time)
        self.ui.chk_fx_limits.clicked.connect(self.draw_impz)
        self.ui.chk_win_time.clicked.connect(self.draw_impz)
        # --- frequency domain plotting ---
        self.ui.cmb_plt_freq_resp.currentIndexChanged.connect(self.draw_impz)
        self.ui.cmb_plt_freq_stim.currentIndexChanged.connect(self.draw_impz)
        self.ui.cmb_plt_freq_stmq.currentIndexChanged.connect(self.draw_impz)        
        self.ui.chk_log_freq.clicked.connect(self._log_mode_freq)
        self.ui.led_log_bottom_freq.editingFinished.connect(self._log_mode_freq)
        self.ui.chk_win_freq.clicked.connect(self.draw_impz)
        
        self.mplwidget_t.mplToolbar.sig_tx.connect(self.process_sig_rx) # connect to toolbar
        self.mplwidget_f.mplToolbar.sig_tx.connect(self.process_sig_rx) # connect to toolbar
        
        # When user has selected a different tab, trigger a recalculation of current tab
        self.tabWidget.currentChanged.connect(self.impz) # passes number of active tab
        # TODO: redraw is sufficient?

        self.sig_rx.connect(self.ui.sig_rx)
        self.ui.sig_tx.connect(self.process_sig_rx) # connect to widgets and signals upstream

#------------------------------------------------------------------------------
    def process_sig_rx_local(self, dict_sig=None):
        """
        Flag signals coming in from local subwidgets with `propagate=True` before 
        proceeding with processing in `process_sig_rx`.
        """
        self.process_sig_rx(dict_sig, propagate=True)

#------------------------------------------------------------------------------
    def process_sig_rx(self, dict_sig=None, propagate=False):
        """
        Process signals coming from the navigation toolbar, local widgets and
        collected from input_tab_widgets
        
        All signals terminate here unless the flag `propagate=True`.
        """
                    
        logger.info("SIG_RX - needs_draw: {0}, visible: {1}\n{2}"\
                     .format(self.needs_draw, self.isVisible(), pprint_log(dict_sig)))
        if dict_sig['sender'] == __name__:
            logger.warning("Stopped infinite loop:\n{0}".format(pprint_log(dict_sig)))
            #return

        if self.isVisible():
            if 'fx_sim' in dict_sig:
                if dict_sig['fx_sim'] == 'get_stimulus':
                    self.fx_set_stimulus(dict_sig) # setup stimulus for fxpoint simulation
                elif dict_sig['fx_sim'] == 'set_results':
                    logger.info("Received fixpoint results.")
                    self.fx_get_results(dict_sig) # plot fx simulation results 
                elif not dict_sig['fx_sim']:
                    logger.error('Missing option for "fx_sim".')
                else:
                    logger.error('Unknown "fx_sim" command option "{0}"\n'\
                                 '\treceived from "{1}"'.format(dict_sig['fx_sim'],dict_sig['sender']))                   

            if 'specs_changed' in dict_sig or 'view_changed' in dict_sig or self.needs_draw:
                self.impz()

            elif 'data_changed' in dict_sig:
                # todo: after 'data_changed' all needs to be set to True except current widget
                self.needs_draw = True
                self.needs_redraw[:] = [True] * 2
                qstyle_widget(self.ui.but_run, "changed")
                self.impz()

            elif 'home' in dict_sig:
                self.redraw()
                # self.tabWidget.currentWidget().redraw() # redraw method of current mplwidget, always redraws tab 0
                self.needs_redraw[self.tabWidget.currentIndex()] = False
            elif 'ui_changed' in dict_sig and dict_sig['ui_changed'] == 'resized'\
                    or self.needs_redraw[self.tabWidget.currentIndex()]:
                self.needs_redraw[:] = [True] * 2
                self.redraw() # redraw current widget

        else:
            if 'data_changed' in dict_sig or 'specs_changed' in dict_sig:
                self.needs_draw = True
            elif 'ui_changed' in dict_sig and dict_sig['ui_changed'] == 'resized':
                self.needs_redraw[:] = [True] * 2
                
        if propagate:
            # signals of local subwidgets are propagated with the name of this widget,
            # global signals terminate here
            dict_sig.update({'sender':__name__})
            self.sig_tx.emit(dict_sig)


# =============================================================================
# Simulation: Calculate stimulus, response and draw them
# =============================================================================

    def impz(self):
        """
        Recalculate response and redraw it
        """
        if True: # self.needs_draw: doesn't work yet - number of data points needs to updated
            self.calc_stimulus()
            self.calc_response()
            self.needs_draw = False
        self.draw_impz()
        #qstyle_widget(self.ui.but_run, "normal")


    def fx_select(self):
        """
        Select between fixpoint and floating point simulation
        """
        self.sim_select = qget_cmb_box(self.ui.cmb_sim_select, data=False)
        self.fx_sim = (self.sim_select == 'Fixpoint')
        self.ui.but_run.setEnabled(self.fx_sim)
        self.ui.chk_fx_scale.setVisible(self.fx_sim)
        self.ui.chk_fx_limits.setVisible(self.fx_sim)
        self.ui.cmb_plt_freq_stmq.setVisible(self.fx_sim)
        self.ui.lbl_plt_freq_stmq.setVisible(self.fx_sim)
        self.ui.cmb_plt_time_stmq.setVisible(self.fx_sim)
        self.ui.lbl_plt_time_stmq.setVisible(self.fx_sim)

        if self.fx_sim:
            qstyle_widget(self.ui.but_run, "changed")
            self.fx_run()
        else:
            self.impz()

    def fx_run(self):
        """
        Run fixpoint simulation
        """        
        self.sig_tx.emit({'sender':__name__, 'fx_sim':'start'})


    def fx_set_stimulus(self, dict_sig):
        """
        - Calculate stimulus # TODO: needed?
        
        - Quantize the stimulus with the selected input quantization settings
        
		- Scale it with the input word length, i.e. with 2**(W-1) (input) to obtain
          integer values # TODO: correct?
          
        - Copy simulation results to `dict_sig` as integer and transfer them to fixpoint filter
        """

        self.calc_stimulus() # calculate selected stimulus with selected length
        # pass stimulus in self.x back  via dict
        self.q_i = fx.Fixed(fb.fil[0]['fxqc']['QI']) # setup quantizer for input quantization
        self.q_i.setQobj({'frmt':'dec'})#, 'scale':'int'}) # always use integer decimal format
        self.x_q =self.q_i.fixp(self.x)
        self.sig_tx.emit({'sender':__name__, 'fx_sim':'set_stimulus', 'fx_stimulus':
                np.round(self.q_i.fixp(self.x) * (1 << self.q_i.WF)).astype(int)})

            
    def fx_get_results(self, dict_sig):
        """
        Get simulation results from `dict_sig` and transfer them to plotting
        routine.
        """
        self.calc_response(dict_sig['fx_results'])
        qset_cmb_box(self.ui.cmb_sim_select, "Fixpoint", fireSignals=True)
        
        #self.sig_tx.emit({'sender':__name__, 'data_changed':'fx_sim'})        

        self.calc_fft()
        self.draw_impz()

#------------------------------------------------------------------------------
    def calc_stimulus(self):
        """
        (Re-)calculate stimulus `self.x`

        Bandlimited periodic functions written by Endolith,
        https://gist.github.com/endolith/407991
        """
        def sawtooth_bl(t):
            """
            Bandlimited sawtooth function as a direct replacement for 
            `scipy.signal.sawtooth`. It is calculated by Fourier synthesis, i.e.
            by summing up all sine wave components up to the Nyquist frequency.
            """
            if t.dtype.char in ['fFdD']:
                ytype = t.dtype.char
            else:
                ytype = 'd'
            y = np.zeros(t.shape, ytype)
            # Get sampling frequency from timebase
            fs =  1 / (t[1] - t[0])
            # Sum all multiple sine waves up to the Nyquist frequency:
            for h in range(1, int(fs*pi)+1):
                y += 2 / pi * -sin(h * t) / h
            return y

        def triang_bl(t):
            """
            Bandlimited triangle function as a direct replacement for 
            `scipy.signal.sawtooth(width=0.5)`. It is calculated by Fourier synthesis, i.e.
            by summing up all sine wave components up to the Nyquist frequency.
            """
            if t.dtype.char in ['fFdD']:
                ytype = t.dtype.char
            else:
                ytype = 'd'
            y = np.zeros(t.shape, ytype)
            # Get sampling frequency from timebase
            fs =  1 / (t[1] - t[0])
            # Sum all multiple sine waves up to the Nyquist frequency:
            for h in range(1, int(fs * pi) + 1, 2):
                y += 8 / pi**2 * -cos(h * t) / h**2            
            return y
            
        def rect_bl(t, duty=0.5):
            """
            Bandlimited rectangular function as a direct replacement for 
            `scipy.signal.square`. It is calculated by Fourier synthesis, i.e.
            by summing up all sine wave components up to the Nyquist frequency.
            """
            if t.dtype.char in ['fFdD']:
                ytype = t.dtype.char
            else:
                ytype = 'd'
            y = np.zeros(t.shape, ytype)
            # Get sampling frequency from timebase
            # Sum all multiple sine waves up to the Nyquist frequency:
            y = sawtooth_bl(t - duty*2*pi) - sawtooth_bl(t) + 2*duty-1
            return y
        def comb_bl(t):
            """
            Bandlimited comb function. It is calculated by Fourier synthesis, i.e.
            by summing up all cosine components up to the Nyquist frequency.
            """
            if t.dtype.char in ['fFdD']:
                ytype = t.dtype.char
            else:
                ytype = 'd'
            y = np.zeros(t.shape, ytype)
            # Get sampling frequency from timebase
            # Sum all multiple sine waves up to the Nyquist frequency:
            fs =  1 / (t[1] - t[0])            
            N = int(fs * pi) + 1
            for h in range(1, N):
                y += cos(h * t)
            y /= N
            return y       
        
        self.n = np.arange(self.ui.N_end)
        self.t = self.n / fb.fil[0]['f_S']
        phi1 = self.ui.phi1 / 180 * pi
        phi2 = self.ui.phi2 / 180 * pi

        # calculate stimuli x[n] ==============================================
        if self.ui.stim == "Pulse":
            self.x = np.zeros(self.ui.N_end)
            self.x[0] = self.ui.A1 # create dirac impulse as input signal
            self.title_str = r'Impulse Response'
            self.H_str = r'$h[n]$' # default
            
        elif self.ui.stim == "None":
            self.x = np.zeros(self.ui.N_end)
            self.title_str = r'System Response to Zero Input'
            self.H_str = r'$h_0[n]$' # default

        elif self.ui.stim == "Step":
            self.x = self.ui.A1 * np.ones(self.ui.N_end) # create step function
            self.title_str = r'Step Response'
            self.H_str = r'$h_{\epsilon}[n]$'
            
        elif self.ui.stim == "StepErr":
            self.x = self.ui.A1 * np.ones(self.ui.N_end) # create step function
            self.title_str = r'Settling Error'
            self.H_str = r'$h_{\epsilon, \infty} - h_{\epsilon}[n]$'
            
        elif self.ui.stim == "Cos":
            self.x = self.ui.A1 * np.cos(2*pi * self.n * self.ui.f1 + phi1) +\
                self.ui.A2 * np.cos(2*pi * self.n * self.ui.f2 + phi2)
            self.title_str = r'System Response to Cosine Signal'
            self.H_str = r'$y[n]$'
                
        elif self.ui.stim == "Sine":
            self.x = self.ui.A1 * np.sin(2*pi * self.n * self.ui.f1 + phi1) +\
                self.ui.A2 * np.sin(2*pi * self.n * self.ui.f2 + phi2)
            self.title_str = r'System Response to Sinusoidal Signal'
            self.H_str = r'$y[n]$'
            
        elif self.ui.stim == "Triang":
            if self.ui.chk_stim_bl.isChecked():
                self.x = self.ui.A1 * triang_bl( 2*pi * self.n * self.ui.f1 + phi1)                
                self.title_str = r'System Response to Bandlimited Triangular Signal'
            else:
                self.x = self.ui.A1 * sig.sawtooth( 2*pi * self.n * self.ui.f1 + phi1, width=0.5)
                self.title_str = r'System Response to Triangular Signal'
            self.H_str = r'$y[n]$'

        elif self.ui.stim == "Saw":
            if self.ui.chk_stim_bl.isChecked():
                self.x = self.ui.A1 * sawtooth_bl( 2*pi * self.n * self.ui.f1 + phi1)
                self.title_str = r'System Response to Bandlimited Sawtooth Signal'                
            else:
                self.x = self.ui.A1 * sig.sawtooth( 2*pi * self.n * self.ui.f1 + phi1)
                self.title_str = r'System Response to Sawtooth Signal'
            self.H_str = r'$y[n]$'

        elif self.ui.stim == "Rect":
            if self.ui.chk_stim_bl.isChecked():
                self.x = self.ui.A1 * rect_bl(2*pi * self.n * self.ui.f1 + phi1, duty=0.5)
                self.title_str = r'System Response to Bandlimited Rect. Signal'                
            else:
                self.x = self.ui.A1 * sig.square(2*pi * self.n * self.ui.f1 + phi1, duty=0.5)
                self.title_str = r'System Response to Rect. Signal'
            self.H_str = r'$y[n]$'

        elif self.ui.stim == "Comb":
            self.x = self.ui.A1 * comb_bl( 2*pi * self.n * self.ui.f1 + phi1)                
            self.title_str = r'System Response to Bandlimited Comb Signal'
            self.H_str = r'$y[n]$'

        else:
            logger.error('Unknown stimulus format "{0}"'.format(self.ui.stim))
            return
        
        # Add noise to stimulus
        if self.ui.noise == "gauss":
            self.x[self.ui.N_start:] += self.ui.noi * np.random.randn(self.ui.N)
            self.title_str += r' w/ Gaussian Noise'           
        elif self.ui.noise == "uniform":
            self.x[self.ui.N_start:] += self.ui.noi * (np.random.rand(self.ui.N)-0.5)
            self.title_str += r' w/ Uniform Noise'
        elif self.ui.noise == "prbs":
            self.x[self.ui.N_start:] += self.ui.noi * 2 * \
                        (np.random.randint(0, 2, self.ui.N)-0.5)
            self.title_str += r' w/ PRBS' 
        # Add DC to stimulus when visible / enabled
        if self.ui.ledDC.isVisible:
            self.x += self.ui.DC
            if self.ui.DC != 0:
                self.title_str += r' and DC'
        
        if self.fx_sim:
            self.title_str = r'$Fixpoint$ ' + self.title_str         
        self.needs_redraw[:] = [True] * 2
        
#------------------------------------------------------------------------------
    def calc_response(self, y_fx = None):
        """
        (Re-)calculate filter response `self.y` from either stimulus `self.x`
        (float mode) or copy fixpoint response. 
        Split response into imag. and real components `self.y_i` and `self.y_r`
        and set the flag `self.cmplx`.
        """
        if self.fx_sim: # use fixpoint simulation results instead of floating results
            if y_fx is not None:
                self.y = np.array(y_fx)
                qstyle_widget(self.ui.but_run, "normal")
            else:
                self.y = None
        else:
            # calculate response self.y_r[n] and self.y_i[n] (for complex case) =====   
            self.bb = np.asarray(fb.fil[0]['ba'][0])
            self.aa = np.asarray(fb.fil[0]['ba'][1])
            if min(len(self.aa), len(self.bb)) < 2:
                logger.error('No proper filter coefficients: len(a), len(b) < 2 !')
                return

            logger.info("Coefficient area = {0}".format(np.sum(np.abs(self.bb))))
    
            sos = np.asarray(fb.fil[0]['sos'])
            antiCausal = 'zpkA' in fb.fil[0]
            causal     = not (antiCausal)
    
            if len(sos) > 0 and causal: # has second order sections and is causal
                y = sig.sosfilt(sos, self.x)
            elif antiCausal:
                y = sig.filtfilt(self.bb, self.aa, self.x, -1, None)
            else: # no second order sections or antiCausals for current filter
                y = sig.lfilter(self.bb, self.aa, self.x)
    
            if self.ui.stim == "StepErr":
                dc = sig.freqz(self.bb, self.aa, [0]) # DC response of the system
                y = y - abs(dc[1]) # subtract DC (final) value from response
    
            self.y = np.real_if_close(y, tol = 1e3)  # tol specified in multiples of machine eps

        self.needs_redraw[:] = [True] * 2

        # Calculate imag. and real components from response
        self.cmplx = np.any(np.iscomplex(self.y))
        if self.cmplx:
            self.y_i = self.y.imag
            self.y_r = self.y.real
        else:
            self.y_r = self.y
            self.y_i = None

#------------------------------------------------------------------------------
    def calc_fft(self):
        """
        (Re-)calculate ffts X(f) and Y(f) of stimulus and response
        """
        #if self.plt_freq_resp != "none":
        # calculate FFT of stimulus / response
        if self.x is None or len(self.x) < self.ui.N_end:
            self.X = np.zeros(self.ui.N_end-self.ui.N_start) # dummy result
            if self.x is None:
                logger.warning("Stimulus is 'None', FFT cannot be calculated.")
            else:
                logger.warning("Length of stimulus is {0} < N = {1}, FFT cannot be calculated."
                           .format(len(self.x), self.ui.N_end))
        else:
            # multiply the  time signal with window function
            x_win = self.x[self.ui.N_start:self.ui.N_end] * self.ui.win
            # calculate absolute value, scale by N_FFT and convert to RMS
            self.X = np.abs(np.fft.fft(x_win)) / (self.ui.N * sqrt(2))
            self.X[0] = self.X[0] * np.sqrt(2) # correct value at DC

            if self.fx_sim:
                # same for fixpoint simulation
                x_q_win = self.q_i.fixp(self.x[self.ui.N_start:self.ui.N_end]) * self.ui.win
                self.X_q = np.abs(np.fft.fft(x_q_win)) / (self.ui.N * sqrt(2))       
                self.X_q[0] = self.X_q[0] * np.sqrt(2) # correct value at DC

        if self.y is None or len(self.y) < self.ui.N_end:
            self.Y = np.zeros(self.ui.N_end-self.ui.N_start) # dummy result
            if self.y is None:
                logger.warning("Transient response is 'None', FFT cannot be calculated.")
            else:
                logger.warning("Length of transient response is {0} < N = {1}, FFT cannot be calculated."
                           .format(len(self.y), self.ui.N_end))             
        else:
            y_win = self.y[self.ui.N_start:self.ui.N_end] * self.ui.win
            self.Y = np.abs(np.fft.fft(y_win)) / (self.ui.N * sqrt(2))
            self.Y[0] = self.Y[0] * np.sqrt(2) # correct value at DC
            
        if self.ui.chk_win_freq.isChecked():
            self.Win = np.abs(np.fft.fft(self.ui.win)) / self.ui.N

        self.needs_redraw[1] = True                
#------------------------------------------------------------------------------
    def update_view(self):
        """
        Only update the limits without recalculating the stimulus and response
        """
        self.draw_impz()

###############################################################################
#        PLOTTING
###############################################################################

    def draw_impz(self):
        """
        (Re-)draw the figure without recalculation
        """
        if not hasattr(self, 'cmplx'): # has response been calculated yet?
            self.calc_stimulus()
            self.calc_response()
            logger.error("Response should have been calculated by now!")
            
        f_unit = fb.fil[0]['freq_specs_unit']
        if f_unit in {"f_S", "f_Ny"}:
            unit_frmt = "i" # italic
        else:
            unit_frmt = None
        self.ui.lblFreqUnit1.setText(to_html(f_unit, frmt=unit_frmt))
        self.ui.lblFreqUnit2.setText(to_html(f_unit, frmt=unit_frmt))
        self.ui.load_fs()
        
        self.scale_i = self.scale_o = 1
        self.fx_min = -1.
        self.fx_max = 1.
        if self.fx_sim: # fixpoint simulation enabled -> scale stimulus and response
            try:
                if self.ui.chk_fx_scale.isChecked():
                    # display stimulus and response as integer values:
                    # - multiply stimulus by 2 ** WF
                    # - display response unscaled
                    self.scale_i = 1 << self.fxqc_dict['QI']['WF']
                    self.fx_min = - (1 << self.fxqc_dict['QO']['W']-1)
                    self.fx_max = -self.fx_min - 1
                else:
                    # display values scaled as "real world values"
                    self.scale_o = 1. / (1 << self.fxqc_dict['QO']['WF'])
                    self.fx_min = -(1 << self.fxqc_dict['QO']['WI'])
                    self.fx_max = -self.fx_min - self.scale_o
                    
            except AttributeError as e:
                logger.error("Attribute error: {0}".format(e))
            except TypeError as e:
                logger.error("Type error: 'fxqc_dict'={0},\n{1}".format(self.fxqc_dict, e))
            except ValueError as e:
                logger.error("Value error: {0}".format(e))
        
        idx = self.tabWidget.currentIndex()
        if idx == 0:
            self.draw_impz_time()
        elif idx == 1:
            self.draw_impz_freq()
        else:
            logger.error("Index {0} out of range!".format(idx))

        #================ Plotting routine time domain =========================
    def _log_mode_time(self):
        """
        Select / deselect log. mode for time domain and update self.ui.bottom_t
        """
        log = self.ui.chk_log_time.isChecked()
        self.ui.lbl_log_bottom_time.setVisible(log)
        self.ui.led_log_bottom_time.setVisible(log)
        self.ui.lbl_dB_time.setVisible(log)
        if log:
            self.ui.bottom_t = safe_eval(self.ui.led_log_bottom_time.text(),
                                         self.ui.bottom_t, return_type='float', sign='neg')
            self.ui.led_log_bottom_time.setText(str(self.ui.bottom_t))
        else:
            self.ui.bottom_t = 0

        self.draw_impz()
        
    def _log_mode_freq(self):
        """
        Select / deselect log. mode for frequency domain and update self.ui.bottom_f
        """

        log = self.ui.chk_log_freq.isChecked()
        self.ui.lbl_log_bottom_freq.setVisible(log)
        self.ui.led_log_bottom_freq.setVisible(log)
        self.ui.lbl_dB_freq.setVisible(log)
        if log:
            self.ui.bottom_f = safe_eval(self.ui.led_log_bottom_freq.text(), 
                                         self.ui.bottom_f, return_type='float',
                                         sign='neg')
            self.ui.led_log_bottom_freq.setText(str(self.ui.bottom_f))
        else:
            self.ui.bottom_f = 0
            
        self.draw_impz()

    def plot_fnc(self, plt_style, ax, plt_dict=None, bottom=0):
        """
        Return a plot method depending on the parameter `plt_style` (str) 
        and the axis instance `ax`. An optional `plt_dict` is modified in place.
        """

        if plt_dict is None:
            plt_dict = {}         
        if plt_style == "line":
            plot_fnc = getattr(ax, "plot")
        elif plt_style == "stem":
            plot_fnc = stems
            plt_dict.update({'ax':ax, 'bottom':bottom})
        elif plt_style == "step":
            plot_fnc = getattr(ax, "plot")
            plt_dict.update({'drawstyle':'steps-mid'})
        elif plt_style == "dots":
            plot_fnc = getattr(ax, "scatter")
        elif plt_style == "none":                
            plot_fnc = no_plot
        else:
            plot_fnc = no_plot
        return plot_fnc


    def _init_axes_time(self):
        """
        Clear the axes of the time domain matplotlib widgets and (re)draw the plots.
        """
        self.plt_time_resp = qget_cmb_box(self.ui.cmb_plt_time_resp, data=False).lower().replace("*","")
        self.plt_time_resp_mkr = "*" in qget_cmb_box(self.ui.cmb_plt_time_resp, data=False)

        self.plt_time_stim = qget_cmb_box(self.ui.cmb_plt_time_stim, data=False).lower().replace("*","")
        self.plt_time_stim_mkr = "*" in qget_cmb_box(self.ui.cmb_plt_time_stim, data=False)

        self.plt_time_stmq = qget_cmb_box(self.ui.cmb_plt_time_stmq, data=False).lower().replace("*","")
        self.plt_time_stmq_mkr = "*" in qget_cmb_box(self.ui.cmb_plt_time_stmq, data=False)

        plt_time = self.plt_time_resp != "none" or self.plt_time_stim != "none" or self.plt_time_stmq != "none"
        
        self.mplwidget_t.fig.clf() # clear figure with axes
            
        if plt_time:
            num_subplots = 1 + (self.cmplx and self.plt_time_resp != "none")
    
            self.mplwidget_t.fig.subplots_adjust(hspace = 0.5)
        
            self.ax_r = self.mplwidget_t.fig.add_subplot(num_subplots,1 ,1)
            self.ax_r.clear()
            self.ax_r.get_xaxis().tick_bottom() # remove axis ticks on top
            self.ax_r.get_yaxis().tick_left() # remove axis ticks right
    
            if self.cmplx and self.plt_time_resp != "none":
                self.ax_i = self.mplwidget_t.fig.add_subplot(num_subplots, 1, 2, sharex = self.ax_r)
                self.ax_i.clear()
                self.ax_i.get_xaxis().tick_bottom() # remove axis ticks on top
                self.ax_i.get_yaxis().tick_left() # remove axis ticks right
    
            if self.ACTIVE_3D: # not implemented / tested yet
                self.ax3d = self.mplwidget_t.fig.add_subplot(111, projection='3d')

    def draw_impz_time(self):
        """
        (Re-)draw the time domain mplwidget
        """

        if self.y is None: # safety net for empty responses
            for ax in self.mplwidget_t.fig.get_axes(): # remove all axes
                self.mplwidget_t.fig.delaxes(ax)
            return

        mkfmt_i = 'd'
        
        self._init_axes_time()

        if self.fx_sim: # fixpoint simulation enabled -> scale stimulus and response
            x_q = self.q_i.fixp(self.x) * self.scale_i
            if self.ui.chk_log_time.isChecked():
                x_q = np.maximum(20 * np.log10(abs(x_q)), self.ui.bottom_t)

            logger.info("self.scale I:{0} O:{1}".format(self.scale_i, self.scale_o))
        else:
            x_q = None

        if self.ui.chk_log_time.isChecked(): # log. scale for stimulus / response time domain
            H_str = '$|$' + self.H_str + '$|$ in dBV'
            x = np.maximum(20 * np.log10(abs(self.x * self.scale_i)), self.ui.bottom_t)
            y = np.maximum(20 * np.log10(abs(self.y_r * self.scale_o)), self.ui.bottom_t)
            win = np.maximum(20 * np.log10(abs(self.ui.win)), self.ui.bottom_t)
            if self.cmplx:
                y_i = np.maximum(20 * np.log10(abs(self.y_i)), self.ui.bottom_t)
                H_i_str = r'$|\Im\{$' + self.H_str + '$\}|$' + ' in dBV'
                H_str =   r'$|\Re\{$' + self.H_str + '$\}|$' + ' in dBV'
            fx_min = 20*np.log10(abs(self.fx_min))
            fx_max = fx_min
        else:
            x = self.x * self.scale_i
            y = self.y_r * self.scale_o
            fx_max = self.fx_max
            fx_min = self.fx_min
            win = self.ui.win
            if self.cmplx:
                y_i = self.y_i * self.scale_o
            
            if self.cmplx:           
                H_i_str = r'$\Im\{$' + self.H_str + '$\}$ in V'
                H_str = r'$\Re\{$' + self.H_str + '$\}$ in V'
            else:
                H_str = self.H_str + ' in V'

        if self.ui.chk_fx_limits.isChecked() and self.fx_sim:
            self.ax_r.axhline(fx_max,0, 1, color='k', linestyle='--')
            self.ax_r.axhline(fx_min,0, 1, color='k', linestyle='--')
                        
        # --------------- Stimulus plot ----------------------------------
        # TODO: local copying of dictionary and modifying is _very_ kludgy
        plot_stim_dict = self.fmt_plot_stim.copy()
        plot_stim_fnc = self.plot_fnc(self.plt_time_stim, self.ax_r, 
                                      plot_stim_dict, self.ui.bottom_t)
        plot_stim_fnc(self.t[self.ui.N_start:], x[self.ui.N_start:], label='$x[n]$',
                 **plot_stim_dict)

        # Add plot markers, this is way faster than normal stem plotting
        if self.plt_time_stim_mkr:
            self.ax_r.scatter(self.t[self.ui.N_start:], x[self.ui.N_start:], **self.fmt_mkr_stim)

        #-------------- Stimulus <q> plot --------------------------------
        if x_q is not None and self.plt_time_stmq != "none":
            plot_stmq_dict = self.fmt_plot_stmq.copy()
            plot_stmq_fnc = self.plot_fnc(self.plt_time_stmq, self.ax_r, 
                                      plot_stmq_dict, self.ui.bottom_t)
            plot_stmq_fnc(self.t[self.ui.N_start:], x_q[self.ui.N_start:], label='$x_q[n]$',
                          **plot_stmq_dict)
            
            if self.plt_time_stmq_mkr:
                self.ax_r.scatter(self.t[self.ui.N_start:], x_q[self.ui.N_start:],
                                  **self.fmt_mkr_stmq)

        # --------------- Response plot ----------------------------------
        plot_resp_dict = self.fmt_plot_resp.copy()
        plot_resp_fnc = self.plot_fnc(self.plt_time_resp, self.ax_r, 
                                      plot_resp_dict, self.ui.bottom_t)
            
        plot_resp_fnc(self.t[self.ui.N_start:], y[self.ui.N_start:], label='$y[n]$',
                 **plot_resp_dict)
        # Add plot markers, this is way faster than normal stem plotting
        if self.plt_time_resp_mkr:
            self.ax_r.scatter(self.t[self.ui.N_start:], y[self.ui.N_start:], **self.fmt_mkr_resp)

        # --------------- Window plot ----------------------------------
        if self.ui.chk_win_time.isChecked():
            self.ax_r.plot(self.t[self.ui.N_start:], win, c="gray", label=self.ui.window_type)

        self.ax_r.legend(loc='best', fontsize = 'small', fancybox=True, framealpha=0.7)

        # --------------- Complex response ----------------------------------
        if self.cmplx and self.plt_time_resp != "none":
            #plot_resp_dict = self.fmt_plot_resp.copy()
            plot_resp_fnc = self.plot_fnc(self.plt_time_resp, self.ax_i,
                                          plot_resp_dict, self.ui.bottom_t)
                
            plot_resp_fnc(self.t[self.ui.N_start:], y_i[self.ui.N_start:], label='$y_i[n]$',
                     **plot_resp_dict)
            # Add plot markers, this is way faster than normal stem plotting
            if self.plt_time_resp_mkr:
                self.ax_i.scatter(self.t[self.ui.N_start:], y_i[self.ui.N_start:], 
                                  marker=mkfmt_i, **self.fmt_mkr_resp)

#            [ml_i, sl_i, bl_i] = self.ax_i.stem(self.t[self.ui.N_start:], y_i[self.ui.N_start:],
#                bottom=self.ui.bottom_t, markerfmt=mkfmt_i, label = '$y_i[n]$')
#            self.ax_i.set_xlabel(fb.fil[0]['plt_tLabel'])
            # self.ax_r.get_xaxis().set_ticklabels([]) # removes both xticklabels
            # plt.setp(ax_r.get_xticklabels(), visible=False) 
            # is shorter but imports matplotlib, set property directly instead:
            [label.set_visible(False) for label in self.ax_r.get_xticklabels()]
            self.ax_r.set_ylabel(H_str + r'$\rightarrow $')
            self.ax_i.set_xlabel(fb.fil[0]['plt_tLabel'])
            self.ax_i.set_ylabel(H_i_str + r'$\rightarrow $')
            self.ax_i.legend(loc='best', fontsize = 'small', fancybox=True, framealpha=0.7)            
        else:
            self.ax_r.set_xlabel(fb.fil[0]['plt_tLabel'])
            self.ax_r.set_ylabel(H_str + r'$\rightarrow $')
        
        self.ax_r.set_title(self.title_str)
        self.ax_r.set_xlim([self.t[self.ui.N_start],self.t[self.ui.N_end-1]])
        expand_lim(self.ax_r, 0.02)
        

        if self.ACTIVE_3D: # not implemented / tested yet
            # plotting the stems
            for i in range(self.ui.N_start, self.ui.N_end):
              self.ax3d.plot([self.t[i], self.t[i]], [y[i], y[i]], [0, y_i[i]],
                             '-', linewidth=2, alpha=.5)

            # plotting a circle on the top of each stem
            self.ax3d.plot(self.t[self.ui.N_start:], y[self.ui.N_start:], y_i[self.ui.N_start:], 'o', markersize=8,
                           markerfacecolor='none', label='$y[n]$')

            self.ax3d.set_xlabel('x')
            self.ax3d.set_ylabel('y')
            self.ax3d.set_zlabel('z')

        self.redraw() # redraw currently active mplwidget

    #--------------------------------------------------------------------------
    def _init_axes_freq(self):
        """
        Clear the axes of the frequency domain matplotlib widgets and 
        calculate the fft
        """
        self.plt_freq_resp = qget_cmb_box(self.ui.cmb_plt_freq_resp, data=False).lower().replace("*","")
        self.plt_freq_resp_mkr = "*" in qget_cmb_box(self.ui.cmb_plt_freq_resp, data=False)

        self.plt_freq_stim = qget_cmb_box(self.ui.cmb_plt_freq_stim, data=False).lower().replace("*","")
        self.plt_freq_stim_mkr = "*" in qget_cmb_box(self.ui.cmb_plt_freq_stim, data=False)

        self.plt_freq_stmq = qget_cmb_box(self.ui.cmb_plt_freq_stmq, data=False).lower().replace("*","")
        self.plt_freq_stmq_mkr = "*" in qget_cmb_box(self.ui.cmb_plt_freq_stmq, data=False)


        self.plt_freq_disabled = self.plt_freq_stim == "none" and self.plt_freq_stmq == "none"\
                                    and self.plt_freq_resp == "none"
       
        if not self.ui.chk_log_freq.isChecked() and len(self.mplwidget_f.fig.get_axes()) == 2:
            self.mplwidget_f.fig.clear() # get rid of second axis when returning from log mode by clearing all

        if len(self.mplwidget_f.fig.get_axes()) == 0: # empty figure, no axes
            self.ax_fft = self.mplwidget_f.fig.add_subplot(111)        
            self.ax_fft.get_xaxis().tick_bottom() # remove axis ticks on top
            self.ax_fft.get_yaxis().tick_left() # remove axis ticks right
            self.ax_fft.set_title("FFT of Transient Response")

        for ax in self.mplwidget_f.fig.get_axes(): # clear but don't delete all axes
            ax.cla()

        if self.ui.chk_log_freq.isChecked() and len(self.mplwidget_f.fig.get_axes()) == 1:
            # create second axis scaled for noise power scale if it doesn't exist yet
            self.ax_fft_noise = self.ax_fft.twinx()
            self.ax_fft_noise.is_twin = True

        self.calc_fft()

    def draw_impz_freq(self):
        """
        (Re-)draw the frequency domain mplwidget
        """
        self._init_axes_freq()
        plt_response = self.plt_freq_resp != "none" 
        plt_stimulus = self.plt_freq_stim != "none" 
        plt_stimulus_q = self.plt_freq_stmq != "none" and self.fx_sim
        
        if not self.plt_freq_disabled:
            if plt_response and not plt_stimulus:
                XY_str = r'$|Y(\mathrm{e}^{\mathrm{j} \Omega})|$'
            elif not plt_response and plt_stimulus:
                XY_str = r'$|X(\mathrm{e}^{\mathrm{j} \Omega})|$'
            else:
                XY_str = r'$|X,Y(\mathrm{e}^{\mathrm{j} \Omega})|$'
            F = np.fft.fftfreq(self.ui.N, d = 1. / fb.fil[0]['f_S'])

        #-----------------------------------------------------------------
        # - Enforce deep copy, scale and convert to RMS by dividing by sqrt(2)
        # - Correct RMS conversion at DC by multiplying with sqrt(2)
        # - Calculate total power P from 
        # - Correct scale for single-sided spectrum (except at DC)
            if plt_stimulus:
                X = self.X.copy() * self.scale_i 
                Px = 2*np.sum(np.square(X[1:])) + np.square(X[0])
                Px /= self.ui.nenbw
                if fb.fil[0]['freqSpecsRangeType'] == 'half':
                    X[1:] = 2 * X[1:]
                    
            if plt_stimulus_q:
                X_q = self.X_q.copy() * self.scale_i 
                Pxq = 2 * np.sum(np.square(X_q[1:])) + np.square(X_q[0])
                Pxq /= self.ui.nenbw
                if fb.fil[0]['freqSpecsRangeType'] == 'half':
                    X_q[1:] = 2 * X_q[1:]

            if plt_response:
                Y = self.Y.copy() * self.scale_o
                Py = np.sum(np.square(Y[1:])) + np.square(Y[0])
                Py /= self.ui.nenbw
                if fb.fil[0]['freqSpecsRangeType'] == 'half':
                    Y[1:] = 2 * Y[1:]

            if self.ui.chk_win_freq.isChecked():
                Win = self.Win.copy()/np.sqrt(2)
                if fb.fil[0]['freqSpecsRangeType'] == 'half':
                    Win[1:] = 2 * Win[1:]

        #-----------------------------------------------------------------
        # Calculate log FFT and power if selected, set units

            if self.ui.chk_log_freq.isChecked():
                unit = unit_P = "dBW"
                unit_nenbw = "dB"
                nenbw = 10 * np.log10(self.ui.nenbw)
                if plt_stimulus:
                    X = np.maximum(20 * np.log10(X), self.ui.bottom_f)
                    Px = 10*np.log10(Px)
                if plt_stimulus_q:
                    X_q = np.maximum(20 * np.log10(X_q), self.ui.bottom_f)
                    Pxq = 10*np.log10(Pxq)
                if plt_response:
                    Y = np.maximum(20 * np.log10(Y), self.ui.bottom_f)
                    Py = 10*np.log10(Py)
                if self.ui.chk_win_freq.isChecked():
                    Win = np.maximum(20 * np.log10(Win), self.ui.bottom_f)
            else:
                unit = "Vrms"
                unit_P = "W"
                unit_nenbw = "bins"
                nenbw = self.ui.nenbw

            XY_str = XY_str + ' in ' + unit

        #-----------------------------------------------------------------
        # Set frequency range 
            if fb.fil[0]['freqSpecsRangeType'] == 'sym':
            # shift X, Y and F by f_S/2
                if plt_response:
                    Y = np.fft.fftshift(Y)
                if plt_stimulus:
                    X = np.fft.fftshift(X)
                if plt_stimulus_q:
                    X_q = np.fft.fftshift(X_q)                    
                if self.ui.chk_win_freq.isChecked():
                    Win = np.fft.fftshift(Win)
                F = np.fft.fftshift(F)
                
            elif fb.fil[0]['freqSpecsRangeType'] == 'half':
                # only use the first half of X, Y and F
                if plt_response:
                    Y = Y[0:self.ui.N//2]
                if plt_stimulus:
                    X = X[0:self.ui.N//2]
                if plt_stimulus_q:
                    X_q = X_q[0:self.ui.N//2]
                if self.ui.chk_win_freq.isChecked():
                    Win = Win[0:self.ui.N//2]
                F = F[0:self.ui.N//2]
                
            else: # fb.fil[0]['freqSpecsRangeType'] == 'whole'
                # plot for F = 0 ... 1
                F = np.fft.fftshift(F) + fb.fil[0]['f_S']/2.

            # --------------- Plot stimulus and response ----------------------
            labels = []

            if plt_stimulus:
                plot_stim_dict = self.fmt_plot_stim.copy()
                plot_stim_fnc = self.plot_fnc(self.plt_freq_stim, self.ax_fft, 
                                              plot_stim_dict, self.ui.bottom_f)
                
                plot_stim_fnc(F, X, label='$Stim.$',**plot_stim_dict)

                if self.plt_freq_stim_mkr:
                    self.ax_fft.scatter(F, X, **self.fmt_mkr_stim)

                labels.append("$P_X$ = {0:.3g} {1}".format(Px, unit_P))

            if plt_stimulus_q:
                plot_stmq_dict = self.fmt_plot_stmq.copy()
                plot_stmq_fnc = self.plot_fnc(self.plt_freq_stmq, self.ax_fft, 
                                              plot_stmq_dict, self.ui.bottom_f)
                
                plot_stmq_fnc(F, X_q, label='$Stim<q>.$',**plot_stmq_dict)

                if self.plt_freq_stmq_mkr:
                    self.ax_fft.scatter(F, X_q, **self.fmt_mkr_stmq)

                labels.append("$P_{{Xq}}$ = {0:.3g} {1}".format(Pxq, unit_P))

            if plt_response:
                plot_resp_dict = self.fmt_plot_resp.copy()
                plot_resp_fnc = self.plot_fnc(self.plt_freq_resp, self.ax_fft,
                                              plot_resp_dict, self.ui.bottom_f)
                
                plot_resp_fnc(F, Y, label='$Resp.$',**plot_resp_dict)

                if self.plt_freq_resp_mkr:
                    self.ax_fft.scatter(F, Y, **self.fmt_mkr_resp)
                
                labels.append("$P_Y$ = {0:.3g} {1}".format(Py, unit_P))

            if self.ui.chk_win_freq.isChecked():
                self.ax_fft.plot(F, Win, c="gray", label="win")
                labels.append("{0}".format(self.ui.window_type))

            labels.append("$NENBW$ = {0:.4g} {1}".format(nenbw, unit_nenbw))
            labels.append("$CGAIN$  = {0:.4g}".format(self.ui.scale))

            # collect all plot objects, hope that the order isn't messed up and add two dummy handles
            # for the NENBW and the CGAIN labels
            handles = self.ax_fft.get_lines()    
            handles.append(mpl_patches.Rectangle((0, 0), 1, 1, fc="white",ec="white", lw=0, alpha=0))
            handles.append(mpl_patches.Rectangle((0, 0), 1, 1, fc="white",ec="white", lw=0, alpha=0))
            self.ax_fft.legend(handles, labels, loc='best', fontsize = 'small',
                               fancybox=True, framealpha=0.7)
            
            self.ax_fft.set_xlabel(fb.fil[0]['plt_fLabel'])
            self.ax_fft.set_ylabel(XY_str)
            self.ax_fft.set_xlim(fb.fil[0]['freqSpecsRange'])
            self.ax_fft.set_title(self.title_str)

            if self.ui.chk_log_freq.isChecked():
                # scale second axis for noise power 
                corr = 10*np.log10(self.ui.N / self.ui.nenbw) 
                mn, mx = self.ax_fft.get_ylim()
                self.ax_fft_noise.set_ylim(mn+corr, mx+corr)
                self.ax_fft_noise.set_ylabel(r'$P_N$ in dBW')

        self.redraw() # redraw currently active mplwidget

#------------------------------------------------------------------------------
    def redraw(self):
        """
        Redraw the currently visible canvas when e.g. the canvas size has changed
        """
        idx = self.tabWidget.currentIndex()
        self.tabWidget.currentWidget().redraw()
        #wdg = getattr(self, self.tab_mplwidgets[idx])
        logger.debug("Redrawing tab {0}".format(idx))
        #wdg_cur.redraw()
        self.needs_redraw[idx] = False
#        self.mplwidget_t.redraw()
#        self.mplwidget_f.redraw()

#------------------------------------------------------------------------------

def main():
    import sys
    from ..compat import QApplication

    app = QApplication(sys.argv)
    mainw = Plot_Impz(None)
    app.setActiveWindow(mainw) 
    mainw.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
    # module test using python -m pyfda.plot_widgets.plot_impz