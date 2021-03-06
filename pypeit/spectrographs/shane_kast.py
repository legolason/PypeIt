""" Module for Shane/Kast specific codes
"""
import numpy as np
import os
from pkg_resources import resource_filename

from astropy.time import Time
from astropy.io import fits

from pypeit import msgs
from pypeit import telescopes
from pypeit.core import framematch
from pypeit.par import pypeitpar
from pypeit.spectrographs import spectrograph
from pypeit.images import detector_container
from pypeit.core import parse

from IPython import embed

class ShaneKastSpectrograph(spectrograph.Spectrograph):
    """
    Child to handle Shane/Kast specific code
    """
    ndet = 1

    def __init__(self):
        # Get it started

        super(ShaneKastSpectrograph, self).__init__()
        self.spectrograph = 'shane_kast'
        self.telescope = telescopes.ShaneTelescopePar()
        #self.timeunit = 'isot'

    @staticmethod
    def default_pypeit_par():
        """
        Set default parameters for Shane Kast reductions.
        """
        par = pypeitpar.PypeItPar()

        # Ignore PCA
        par['calibrations']['slitedges']['sync_predict'] = 'nearest'

        # Always correct for flexure, starting with default parameters
        par['flexure']['spec_method'] = 'boxcar'
        # Set the default exposure time ranges for the frame typing
        par['calibrations']['biasframe']['exprng'] = [None, 1]
        par['calibrations']['darkframe']['exprng'] = [999999, None]     # No dark frames
        par['calibrations']['pinholeframe']['exprng'] = [999999, None]  # No pinhole frames
        par['calibrations']['pixelflatframe']['exprng'] = [0, None]
        par['calibrations']['traceframe']['exprng'] = [0, None]
        par['calibrations']['arcframe']['exprng'] = [None, 61]
        par['calibrations']['standardframe']['exprng'] = [1, 61]
        #
        par['scienceframe']['exprng'] = [61, None]
        return par

    def compound_meta(self, headarr, meta_key):
        if meta_key == 'mjd':
            time = headarr[0]['DATE']
            ttime = Time(time, format='isot')
            return ttime.mjd
        else:
            msgs.error("Not ready for this compound meta")

    def init_meta(self):
        """
        Generate the meta data dict
        Note that the children can add to this

        Returns:
            self.meta: dict (generated in place)

        """
        meta = {}
        # Required (core)
        meta['ra'] = dict(ext=0, card='RA')
        meta['dec'] = dict(ext=0, card='DEC')
        meta['target'] = dict(ext=0, card='OBJECT')
        # dispname is arm specific (blue/red)
        meta['decker'] = dict(ext=0, card='SLIT_N')
        meta['binning'] = dict(ext=0, card=None, default='1,1')
        meta['mjd'] = dict(ext=0, card=None, compound=True)
        meta['exptime'] = dict(ext=0, card='EXPTIME')
        meta['airmass'] = dict(ext=0, card='AIRMASS')
        # Additional ones, generally for configuration determination or time
        meta['dichroic'] = dict(ext=0, card='BSPLIT_N')
        lamp_names = [ '1', '2', '3', '4', '5',
                       'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K']
        for kk,lamp_name in enumerate(lamp_names):
            meta['lampstat{:02d}'.format(kk+1)] = dict(ext=0, card='LAMPSTA{0}'.format(lamp_name))
        # Ingest
        self.meta = meta

    def configuration_keys(self):
        """
        Set the configuration keys

        Returns:
            cfg_keys: list

        """
        # decker is not included because arcs are often taken with a 0.5" slit
        return ['dispname', 'dichroic' ]

    def check_frame_type(self, ftype, fitstbl, exprng=None):
        """
        Check for frames of the provided type.
        """
        good_exp = framematch.check_frame_exptime(fitstbl['exptime'], exprng)
        if ftype in ['science', 'standard']:
            return good_exp & self.lamps(fitstbl, 'off')
#            \
#                        & np.array([ t not in ['Arcs', 'Bias', 'Dome Flat']
#                                        for t in fitstbl['target']])
        if ftype == 'bias':
            return good_exp # & (fitstbl['target'] == 'Bias')
        if ftype in ['pixelflat', 'trace', 'illumflat']:
            # Flats and trace frames are typed together
            return good_exp & self.lamps(fitstbl, 'dome') # & (fitstbl['target'] == 'Dome Flat')
        if ftype in ['pinhole', 'dark']:
            # Don't type pinhole or dark frames
            return np.zeros(len(fitstbl), dtype=bool)
        if ftype in ['arc', 'tilt']:
            return good_exp & self.lamps(fitstbl, 'arcs')#  & (fitstbl['target'] == 'Arcs')

        msgs.warn('Cannot determine if frames are of type {0}.'.format(ftype))
        return np.zeros(len(fitstbl), dtype=bool)
  
    def lamps(self, fitstbl, status):
        """
        Check the lamp status.

        Args:
            fitstbl (:obj:`astropy.table.Table`):
                The table with the fits header meta data.
            status (:obj:`str`):
                The status to check.  Can be `off`, `arcs`, or `dome`.
        
        Returns:
            numpy.ndarray: A boolean array selecting fits files that
            meet the selected lamp status.

        Raises:
            ValueError:
                Raised if the status is not one of the valid options.
        """
        if status == 'off':
            # Check if all are off
            return np.all(np.array([ (fitstbl[k] == 'off') | (fitstbl[k] == 'None')
                                        for k in fitstbl.keys() if 'lampstat' in k]), axis=0)
        if status == 'arcs':
            # Check if any arc lamps are on
            arc_lamp_stat = [ 'lampstat{0:02d}'.format(i) for i in range(6,17) ]
            return np.any(np.array([ fitstbl[k] == 'on' for k in fitstbl.keys()
                                            if k in arc_lamp_stat]), axis=0)
        if status == 'dome':
            # Check if any dome lamps are on
            dome_lamp_stat = [ 'lampstat{0:02d}'.format(i) for i in range(1,6) ]
            return np.any(np.array([ fitstbl[k] == 'on' for k in fitstbl.keys()
                                            if k in dome_lamp_stat]), axis=0)
        raise ValueError('No implementation for status = {0}'.format(status))

class ShaneKastBlueSpectrograph(ShaneKastSpectrograph):
    """
    Child to handle Shane/Kast blue specific code
    """
    def __init__(self):
        # Get it started
        super(ShaneKastBlueSpectrograph, self).__init__()
        self.spectrograph = 'shane_kast_blue'
        self.camera = 'KASTb'
        # Uses timeunit from parent class
        # Uses default primary_hdrext
        self.sky_file = 'sky_kastb_600.fits'

    def get_detector_par(self, hdu, det):
        """
        Return a DectectorContainer for the current image

        Args:
            hdu (`astropy.io.fits.HDUList`):
                HDUList of the image of interest.
                Ought to be the raw file, or else..
            det (int):

        Returns:
            :class:`pypeit.images.detector_container.DetectorContainer`:

        """

        # Detector 1
        detector_dict = dict(
            binning=self.get_meta_value(self.get_headarr(hdu), 'binning'),
            det=1,
            dataext=0,
            specaxis=1,
            specflip=False,
            spatflip=False,
            platescale=0.43,
            saturation=65535.,
            mincounts=-1e10,
            nonlinear=0.76,
            numamplifiers=2,
            gain=np.asarray([1.2, 1.2]),
            ronoise=np.asarray([3.7, 3.7]),
            xgap=0.,
            ygap=0.,
            ysize=1.,
            darkcurr=0.0,
            datasec=np.asarray(['[:, 1:1024]', '[:, 1025:2048]']),  # These are rows, columns on the raw frame, 1-indexed
            oscansec=np.asarray(['[:, 2050:2080]', '[:, 2081:2111]']),
        )
        # suffix='_blue'
        detector = detector_container.DetectorContainer(**detector_dict)

        # Return
        return detector

    def default_pypeit_par(self):
        """
        Set default parameters for Shane Kast Blue reductions.
        """
        par = ShaneKastSpectrograph.default_pypeit_par()
        par['rdx']['spectrograph'] = 'shane_kast_blue'
        par['flexure']['spectrum'] = os.path.join(resource_filename('pypeit', 'data/sky_spec/'),
                                                  'sky_kastb_600.fits')
        # 1D wavelength solution
        par['calibrations']['wavelengths']['sigdetect'] = 5.
        par['calibrations']['wavelengths']['rms_threshold'] = 0.20
        par['calibrations']['wavelengths']['lamps'] = ['CdI','HgI','HeI']

        par['calibrations']['wavelengths']['method'] = 'full_template'
        par['calibrations']['wavelengths']['n_first'] = 3
        par['calibrations']['wavelengths']['match_toler'] = 2.5
        #par['calibrations']['wavelengths']['nonlinear_counts'] = self.detector[0]['nonlinear'] * self.detector[0]['saturation']

        # Set wave tilts order
        par['calibrations']['tilts']['spat_order'] = 3
        par['calibrations']['tilts']['spec_order'] = 5
        par['calibrations']['tilts']['maxdev_tracefit'] = 0.02
        par['calibrations']['tilts']['maxdev2d'] = 0.02

        return par

    def config_specific_par(self, scifile, inp_par=None):
        """
        Modify the PypeIt parameters to hard-wired values used for
        specific instrument configurations.

        .. todo::
            Document the changes made!

        Args:
            scifile (str):
                File to use when determining the configuration and how
                to adjust the input parameters.
            inp_par (:class:`pypeit.par.parset.ParSet`, optional):
                Parameter set used for the full run of PypeIt.  If None,
                use :func:`default_pypeit_par`.

        Returns:
            :class:`pypeit.par.parset.ParSet`: The PypeIt paramter set
            adjusted for configuration specific parameter values.
        """
        par = self.default_pypeit_par() if inp_par is None else inp_par
        # TODO: Should we allow the user to override these?

        if self.get_meta_value(scifile, 'dispname') == '600/4310':
            par['calibrations']['wavelengths']['reid_arxiv'] = 'shane_kast_blue_600.fits'
        elif self.get_meta_value(scifile, 'dispname') == '452/3306':
            par['calibrations']['wavelengths']['reid_arxiv'] = 'shane_kast_blue_452.fits'
        elif self.get_meta_value(scifile, 'dispname') == '830/3460':  # NOT YET TESTED
            par['calibrations']['wavelengths']['reid_arxiv'] = 'shane_kast_blue_830.fits'
        else:
            msgs.error("NEED TO ADD YOUR GRISM HERE!")
        # Return
        return par


    def init_meta(self):
        """
        Meta data specific to shane_kast_blue

        Returns:

        """
        super(ShaneKastBlueSpectrograph, self).init_meta()
        # Add the name of the dispersing element
        # dispangle and filter1 are not defined for Shane Kast Blue

        # Required
        self.meta['dispname'] = dict(ext=0, card='GRISM_N')
        # Additional (for config)


class ShaneKastRedSpectrograph(ShaneKastSpectrograph):
    """
    Child to handle Shane/Kast red specific code
    """
    def __init__(self):

        # Get it started
        super(ShaneKastRedSpectrograph, self).__init__()
        self.spectrograph = 'shane_kast_red'
        self.camera = 'KASTr'

    def get_detector_par(self, hdu, det):
        """
        Return a DectectorContainer for the current image

        Args:
            hdu (`astropy.io.fits.HDUList`):
                HDUList of the image of interest.
                Ought to be the raw file, or else..
            det (int):

        Returns:
            :class:`pypeit.images.detector_container.DetectorContainer`:

        """
        # Binning
        binning = self.get_meta_value(self.get_headarr(hdu), 'binning')  # Could this be detector dependent??

        # Detector 1
        detector_dict = dict(
            binning         = binning,
            det             = 1,
            dataext         = 0,
            specaxis        = 0,
            specflip        = False,
            spatflip        = False,
            platescale      = 0.43,
            darkcurr        = 0.0,
            saturation      = 65535.,
            nonlinear       = 0.76,
            mincounts       = -1e10,
            numamplifiers   = 2,
            gain            = np.atleast_1d([1.9, 1.9]),
            ronoise         = np.atleast_1d([3.8, 3.8]),
            )

        # Parse datasec, oscancsec from the header
        header = hdu[0].header
        naxis1 = header['NAXIS1']
        crval1u = header['CRVAL1U']
        nover = header['COVER']

        ndata = naxis1 - nover*2

        x1_0 = 1             # Amp 1
        x1_1 = 512 - crval1u
        x2_0 = x1_1+1        # Amp
        x2_1 = ndata

        xo1_1 = x2_1+1
        xo1_2 = x2_1+nover
        xo2_1 = xo1_2+1
        xo2_2 = xo1_2+nover

        datasec = ['[:,{}:{}]'.format(x1_0, x1_1), '[:,{}:{}]'.format(x2_0,x2_1)]    # These are rows, columns on the raw frame, 1-indexed
        oscansec = ['[:,{}:{}]'.format(xo1_1,xo1_2), '[:,{}:{}]'.format(xo2_1,xo2_2)]

        # Fill it up
        detector_dict['datasec'] = np.atleast_1d(datasec)
        detector_dict['oscansec'] = np.atleast_1d(oscansec)

        return detector_container.DetectorContainer(**detector_dict)


    def default_pypeit_par(self):
        """
        Set default parameters for Shane Kast Red reductions.
        """
        par = ShaneKastSpectrograph.default_pypeit_par()
        par['rdx']['spectrograph'] = 'shane_kast_red'

        # 1D wavelength solution
        par['calibrations']['wavelengths']['lamps'] = ['NeI','HgI','HeI','ArI']
        #par['calibrations']['wavelengths']['nonlinear_counts'] = self.detector[0]['nonlinear'] * self.detector[0]['saturation']

        return par

    def init_meta(self):
        """
        Meta data specific to shane_kast_red

        Returns:

        """
        super(ShaneKastRedSpectrograph, self).init_meta()
        # Add the name of the dispersing element
        # dispangle is not defined for Shane Kast Blue

        # Required
        self.meta['dispname'] = dict(ext=0, card='GRATNG_N')
        self.meta['dispangle'] = dict(ext=0, card='GRTILT_P', rtol=1e-3)
        # Additional (for config)

    def configuration_keys(self):
        """
        Return the metadata keys that defines a unique instrument
        configuration.

        This list is used by :class:`pypeit.metadata.PypeItMetaData` to
        identify the unique configurations among the list of frames read
        for a given reduction.

        Returns:

            list: List of keywords of data pulled from meta
        """
        cfg_keys = super(ShaneKastRedSpectrograph, self).configuration_keys()
        # Add grating tilt
        return cfg_keys+['dispangle']

class ShaneKastRedRetSpectrograph(ShaneKastSpectrograph):
    """
    Child to handle Shane/Kast red specific code
    """
    def __init__(self):
        # Get it started
        super(ShaneKastRedRetSpectrograph, self).__init__()
        self.spectrograph = 'shane_kast_red_ret'
        # WARNING: This is not unique wrt ShaneKastRed...
        self.camera = 'KASTr'

    def get_detector_par(self, hdu, det):
        """
        Return a DectectorContainer for the current image

        Args:
            hdu (`astropy.io.fits.HDUList`):
                HDUList of the image of interest.
                Ought to be the raw file, or else..
            det (int):

        Returns:
            :class:`pypeit.images.detector_container.DetectorContainer`:

        """
        # Binning
        binning = self.get_meta_value(self.get_headarr(hdu), 'binning')  # Could this be detector dependent??

        # Detector 1
        detector_dict = dict(
            binning         = binning,
            det             = 1,
            dataext         = 0,
            specaxis        = 1,
            specflip        = False,
            spatflip        = False,
            platescale      = 0.774,
            darkcurr        = 0.0,
            saturation      = 120000., # JFH adjusted to this level as the flat are otherwise saturated
            nonlinear       = 0.76,
            mincounts       = -1e10,
            numamplifiers   = 1,
            gain            = np.atleast_1d(3.0),
            ronoise         = np.atleast_1d(12.5),
            datasec         = np.atleast_1d('[:,1:1200]'),
            oscansec        = np.atleast_1d('[:,1203:1232]'),
         )

        return detector_container.DetectorContainer(**detector_dict)

    def default_pypeit_par(self):
        """
        Set default parameters for Shane Kast Red Ret reductions.
        """
        par = ShaneKastSpectrograph.default_pypeit_par()
        par['rdx']['spectrograph'] = 'shane_kast_red_ret'

        # 1D wavelength solution
        par['calibrations']['wavelengths']['lamps'] = ['NeI', 'HgI', 'HeI', 'ArI']
        #par['calibrations']['wavelengths']['nonlinear_counts'] = self.detector[0]['nonlinear'] * self.detector[0]['saturation']
        par['calibrations']['wavelengths']['sigdetect'] = 5.

        return par

    def check_header(self, headers):
        """
        Check headers match expectations for a Shane Kast Red Ret
        exposure.

        See also
        :func:`pypeit.spectrographs.spectrograph.Spectrograph.check_headers`.

        Args:
            headers (list):
                A list of headers read from a fits file
        """
        expected_values = {   '0.NAXIS': 2,
                            '0.DSENSOR': 'Ret 400x1200' }
        super(ShaneKastRedRetSpectrograph, self).check_headers(headers,
                                                               expected_values=expected_values)

    def init_meta(self):
        """
        Meta data specific to shane_kast_blue

        Returns:

        """
        super(ShaneKastRedRetSpectrograph, self).init_meta()
        # Add the name of the dispersing element
        # dispangle and filter1 are not defined for Shane Kast Blue

        # Required
        self.meta['dispname'] = dict(ext=0, card='GRATNG_N')
        self.meta['dispangle'] = dict(ext=0, card='GRTILT_P')
        # Additional (for config)

