import sys
import pdb
import numpy as np
import arsciexp
import artrace
import armsgs as msgs
import arsort
import arproc
import arqa


def ARMLSD(argflag, spect, fitsdict, reuseMaster=False):
    """
    Automatic Reduction and Modeling of Long Slit Data

    Parameters
    ----------
    argflag : dict
      Arguments and flags used for reduction
    spect : dict
      Properties of the spectrograph.
    fitsdict : dict
      Contains relevant information from fits header files
    reuseMaster : bool
      If True, a master frame that will be used for another science frame
      will not be regenerated after it is first made.
      This setting comes with a price, and if a large number of science frames are
      being generated, it may be more efficient to simply regenerate the master
      calibrations on the fly.

    Returns
    -------
    status : int
      Status of the reduction procedure
      0 = Successful execution
      1 = ...
    """
    status = 0

    # Create a list of science exposure classes
    sciexp = SetupScience(argflag, spect, fitsdict)
    numsci = len(sciexp)

    # Start reducing the data
    for sc in range(numsci):
        slf = sciexp[sc]
        scidx = slf._idx_sci[0]
        msgs.info("Reducing file {0:s}, target {1:s}".format(fitsdict['filename'][scidx], slf._target_name))
        # Loop on Detectors
        for kk in xrange(slf._spect['mosaic']['ndet']):
            det = kk + 1  # Detectors indexed from 1
            ###############
            # Get amplifier sections
            fitsdict = arproc.get_ampsec_trimmed(slf, fitsdict, det, scidx)
            ###############
            # Generate master bias frame
            update = slf.MasterBias(fitsdict, det)
            if update and reuseMaster: UpdateMasters(sciexp, sc, det, ftype="bias")
            ###############
            # Generate a bad pixel mask (should not repeat)
            update = slf.BadPixelMask(det)
            if update and reuseMaster: UpdateMasters(sciexp, sc, det, ftype="arc")
            ###############
            # Estimate gain and readout noise for the amplifiers
            msgs.work("Estimate Gain and Readout noise from the raw frames...")
            ###############
            # Generate a master arc frame
            update = slf.MasterArc(fitsdict, det)
            if update and reuseMaster: UpdateMasters(sciexp, sc, det, ftype="arc")
            ###############
            # Determine the dispersion direction (and transpose if necessary)
            slf.GetDispersionDirection(fitsdict, det)
            if slf._bpix[det-1] is None:
                slf.SetMasterFrame(np.zeros((slf._nspec[det-1], slf._nspat[det-1])), "badpix", det)
            ###############
            # Generate a master trace frame
            update = slf.MasterTrace(fitsdict, det)
            if update and reuseMaster: UpdateMasters(sciexp, sc, det, ftype="trace")
            ###############
            # Generate an array that provides the physical pixel locations on the detector
            slf.GetPixelLocations(det)
            ###############
            # Determine the edges of the spectrum (spatial)
            lordloc, rordloc, extord = artrace.trace_orders(slf, slf._mstrace[det-1], det, singleSlit=True,
                                                                      pcadesc="PCA trace of the slit edges")
            slf.SetArray(slf._lordloc, lordloc, det)
            slf.SetArray(slf._rordloc, rordloc, det)
            # Convert physical trace into a pixel trace
            msgs.info("Converting physical trace locations to nearest pixel")
            pixcen  = artrace.phys_to_pix(0.5*(slf._lordloc[det-1]+slf._rordloc[det-1]), slf._pixlocn[det-1], 1)
            pixwid  = (slf._rordloc[det-1]-slf._lordloc[det-1]).mean(0).astype(np.int)
            lordpix = artrace.phys_to_pix(slf._lordloc[det-1], slf._pixlocn[det-1], 1)
            rordpix = artrace.phys_to_pix(slf._rordloc[det-1], slf._pixlocn[det-1], 1)
            slf.SetArray(slf._pixcen, pixcen, det)
            slf.SetArray(slf._pixwid, pixwid, det)
            slf.SetArray(slf._lordpix, lordpix, det)
            slf.SetArray(slf._rordpix, rordpix, det)
            # Save QA for slit traces
            arqa.slit_trace_qa(slf, slf._mstrace[det-1], slf._lordpix[det-1], slf._rordpix[det-1], extord, desc="Trace of the slit edges")

            slf._qa.close()
            msgs.error("UP TO HERE -- REMOVE QA CLOSE")
            pdb.set_trace()
        # Free up some memory by replacing the reduced ScienceExposure class
        # Close the QA for this object
        slf._qa.close()
        sciexp[sc] = None
    return status


def SetupScience(argflag, spect, fitsdict):
    """
    Create an exposure class for every science frame

    Parameters
    ----------
    argflag : dict
      Arguments and flags used for reduction
    spect : dict
      Properties of the spectrograph.
    fitsdict : dict
      Contains relevant information from fits header files

    Returns
    -------
    sciexp : list
      A list containing all science exposure classes
    """

    # Sort the data
    msgs.bug("Files and folders should not be deleted -- there should be an option to overwrite files automatically if they already exist, or choose to rename them if necessary")
    filesort = arsort.sort_data(argflag, spect, fitsdict)
    # Write out the details of the sorted files
    if argflag['out']['sorted'] is not None: arsort.sort_write(argflag['out']['sorted'], spect, fitsdict, filesort)
    # Match calibration frames to science frames
    spect = arsort.match_science(argflag, spect, fitsdict, filesort)
    # If the user is only debugging, then exit now
    if argflag['run']['calcheck']:
        msgs.info("Calibration check complete. Change the 'calcheck' flag to continue with data reduction")
        sys.exit()
    # Make directory structure for different objects
    sci_targs = arsort.make_dirs(argflag, fitsdict, filesort)
    # Create the list of science exposures
    numsci = np.size(filesort['science'])
    sciexp = []
    for i in xrange(numsci): sciexp.append(arsciexp.ScienceExposure(i, argflag, spect, fitsdict, filesort))
    return sciexp


def UpdateMasters(sciexp, sc, det, ftype=None):
    """
    Update the master calibrations for other science targets, if they
    will use an identical master frame

    Parameters
    ----------
    sciexp : list
      A list containing all science exposure classes
    sc : int
      Index of sciexp for the science exposure currently being reduced
    det : int
      detector index (starting from 1)
    ftype : str
      Describes the type of Master frame being udpated
    """
    numsci = len(sciexp)
    if ftype == "arc": chkarr = sciexp[sc]._idx_arcs
    elif ftype == "bias": chkarr = sciexp[sc]._idx_bias
    elif ftype == "trace": chkarr = sciexp[sc]._idx_trace
    else:
        msgs.bug("I could not update frame of type: {0:s}".format(ftype))
        return
    for i in xrange(sc+1,numsci):
        # Check if an *identical* master frame has already been produced
        if ftype == "arc": chkfarr = sciexp[i]._idx_arcs
        elif ftype == "bias": chkfarr = sciexp[i]._idx_bias
        elif ftype == "trace": chkfarr = sciexp[i]._idx_trace
        if np.array_equal(chkarr, chkfarr):
            msgs.info("Updating master {0:s} frame for science target {1:d}/{2:d}".format(ftype, i+1, numsci))
            sciexp[i].SetMasterFrame(sciexp[sc].GetMasterFrame(ftype, det), ftype, det)
    return
