#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recenters, detects bad frames, crops and bins

@author: Iain
"""
__author__ = 'Iain Hammond'
__all__ = ['calib_dataset']

import os
import pathlib
from os.path import isfile

import numpy as np
import pyprind
from matplotlib import pyplot as plt

from vip_hci.conf import get_available_memory, time_ini, timing
from vip_hci.fits import open_fits, write_fits
from vip_hci.preproc import cube_recenter_via_speckles, cube_recenter_2dfit, frame_shift, cube_detect_badfr_correlation, \
    cube_crop_frames
from vip_hci.stats import cube_distance


class calib_dataset:  # this class is for pre-processing of the calibrated data
    def __init__(self, inpath, outpath, dataset_dict, recenter_method, recenter_model, coro=True):
        self.inpath = inpath
        self.outpath = outpath
        self.derot_angles_cropped = open_fits(self.inpath+'derot_angles_cropped.fits', verbose=False)
        self.recenter_method = recenter_method
        self.recenter_model = recenter_model
        self.sci_list = []
        # get all the science cubes into a list
        with open(self.inpath+'sci_list.txt', "r") as f:
            tmp = f.readlines()
            for line in tmp:
                self.sci_list.append(line.split('\n')[0])
        self.sci_list.sort()  # make sure they are in order so derotation doesn't make a mess of the frames
        print(len(self.sci_list), 'science cubes')
        # read the dimensions of each science cube from calibration, or get from each fits file
        if isfile(self.inpath+'new_ndit_sci_sky_unsat.fits'):
            print('Using SCI cube dimensions from calibration')
            nframes = open_fits(self.inpath+'new_ndit_sci_sky_unsat.fits', verbose=False)
            self.real_ndit_sci = [int(nframes[0])] * len(self.sci_list)
        else:
            self.real_ndit_sci = []
            print('Re-evaluating SCI cube dimensions')
            for sc, fits_name in enumerate(self.sci_list):  # enumerate over the list of all science cubes
                tmp = open_fits(self.inpath+'4_sky_subtr_imlib_'+fits_name, verbose=False)
                self.real_ndit_sci.append(tmp.shape[0])  # gets length of each cube for later use
                del tmp
        self.dataset_dict = dataset_dict
        self.fast_reduction = dataset_dict['fast_reduction']
        os.system("cp " + self.inpath + 'master_unsat-stellarpsf_fluxes.fits ' + self.outpath)  # for use later
        os.system("cp " + self.inpath + 'fwhm.fits ' + self.outpath)  # for use later
        os.system("cp " + self.inpath + 'master_unsat_psf_norm.fits ' + self.outpath)  # for use later

    def recenter(self, nproc=1, sigfactor=4, subi_size=41, crop_sz=251, verbose=True, debug=False, plot=False, coro=True):
        """
        Recenters cropped science images by fitting a double Gaussian (negative+positive) to each median combined SCI cube,
        or by fitting a single negative Gaussian to the coronagraph using the speckle pattern of each median combined SCI cube.
        
        Parameters:
        ----------
        sigfactor: float, default = 4
            If thresholding is performed during 2gauss fitting, set the threshold in terms of gaussian sigma in the
            subimage (will depend on your cropping size)
        subi_size: int, default = 21
            Size of the square subimage sides in pixels.
        crop_sz: int, optional, in units of pixels. 251 by default
            Crops to this size after recentring for memory management purposes. Useful for very large datasets
        verbose: bool
            To provide extra information about the progress and results of the pipeline
        plot: bool
            If True, a plot of the shifts is saved (PDF)
        coro: bool
            For coronagraph data. False otherwise. Recentring requires coronagraphic data
        
        Writes fits to file:
        ----------
        x_shifts.fits # writes the x shifts to the file
        y_shifts.fits # writes the y shifts to the file
        {source}_master_cube.fits # makes the recentered master cube
        derot_angles.fits # makes a vector of derotation angles
        """  	
        pathlib.Path(self.outpath).mkdir(parents=True, exist_ok=True)

        if not coro:
            if self.recenter_method != '2dfit':
                raise ValueError('Recentering method invalid')
            if self.recenter_model == '2gauss':
                raise ValueError('2Gauss requires coronagraphic data')
        
        ncubes = len(self.sci_list)     
         
        fwhm_all = open_fits(self.inpath+'fwhm.fits', verbose=debug) # changed this to open the file as sometimes we wont run get_stellar_psf() or it may have already run
        fwhm = fwhm_all[0] # fwhm is the first entry in the file 
        fwhm = fwhm.item() # changes from numpy.float32 to regular float so it will work in VIP
        if verbose:
            print('FWHM = {:3f} px of type: {}'.format(fwhm,type(fwhm)))

        if not subi_size % 2:
            subi_size -= 1
            print('WARNING: Recentring sub image size not odd. Adjusted to {} px'.format(subi_size))

        # Creates a master science cube with just the median of each cube
        if not isfile(self.outpath+'median_calib_cube.fits'):
            bar = pyprind.ProgBar(len(self.sci_list), stream=1, title='Creating master science cube (median of each science cube)....')
            for sc, fits_name in enumerate(self.sci_list):  # enumerate over the list of all science cubes
                tmp = open_fits(self.inpath+'4_sky_subtr_imlib_'+fits_name, verbose=debug)  # open cube as tmp
                if sc == 0:
                    _, ny, nx = tmp.shape  # dimensions of cube
                    if subi_size > ny:  # check if bigger than science frame
                        subi_size = ny  # ny should be odd already from calibration
                        print('WARNING: Recentring sub image size larger than frame. Adjusted to {} px'.format(subi_size))
                    tmp_tmp = np.zeros([ncubes, ny, ny])  # template cube with the median of each SCI cube
                tmp_tmp[sc] = np.median(tmp, axis=0)  # median frame of cube tmp
                get_available_memory()
                bar.update()
            write_fits(self.outpath+'median_calib_cube.fits', tmp_tmp, verbose=debug)
            if verbose:
                print('Median science cube created for recentring')
        else:
            tmp_tmp = open_fits(self.outpath+'median_calib_cube.fits', verbose=debug)
            _, ny, nx = tmp_tmp.shape
            if verbose:
                print('Median science cube for recentring has been read from file')

        if self.recenter_method == 'speckle':
                # FOR GAUSSIAN
                print('##### Recentering via speckle pattern #####', flush=True)
                #registered science sube, low+high pass filtered cube,cube with stretched values, x shifts, y shifts
                if debug:
                    get_available_memory()
                recenter = cube_recenter_via_speckles(tmp_tmp, cube_ref=None,
                                                      alignment_iter=5, gammaval=1,
                                                      min_spat_freq=0.5, max_spat_freq=3,
                                                      fwhm=fwhm, debug=debug,
                                                      recenter_median=True, negative=coro,
                                                      fit_type='gaus', crop=True, subframesize=subi_size,
                                                      imlib='opencv', interpolation='lanczos4', plot=plot, full_output=True)
                sy = recenter[4]
                sx = recenter[3]
        elif self.recenter_method == '2dfit':	
                # DOUBLE GAUSSIAN
                print('##### Recentering via 2dfit #####', flush=True)
                if debug:
                    get_available_memory()
                params_2g = {'fwhm_neg': 0.8*fwhm, 'fwhm_pos': 2*fwhm, 'theta_neg': 48., 'theta_pos':135., 'neg_amp': 0.8}
                recenter = cube_recenter_2dfit(tmp_tmp, xy=None, fwhm=fwhm, subi_size=subi_size,
                                               model=self.recenter_model, nproc=nproc, imlib='opencv',
                                               interpolation='lanczos4', offset=None,
                                               negative=False, threshold=True, sigfactor=sigfactor,
                                               fix_neg=False, params_2g=params_2g,
                                               save_shifts=False, full_output=True, verbose=verbose,
                                               debug=debug, plot=plot)
                sy = recenter[1]
                sx = recenter[2]
        else:
            raise ValueError('Recentring method is not recognised. Use either speckle or 2dfit.')
        if plot:  # save the shift plot
            plt.savefig(self.outpath+'shifts-xy.pdf', format='pdf')
            plt.close('all')
        del recenter
        print('Recentring complete', flush=True)
        if debug:
            get_available_memory()
#                true_agpm_cen = (res[4][0],res[3][0])
#                true_fwhm_pos = (res[5][0],res[6][0])
#                true_fwhm_neg = (res[7][0],res[8][0])
#                true_theta_pos = res[9][0]
#                true_theta_neg = res[10][0]
#                amp_pos = res[11][0]
#                amp_neg = res[12][0]
#                true_neg_amp = amp_neg/amp_pos
#                params_2g = {'fwhm_neg': true_fwhm_neg, 'fwhm_pos': true_fwhm_pos, 
#			                 'theta_neg': true_theta_neg, 'theta_pos':true_theta_pos, 
#			                 'neg_amp': true_neg_amp}
#		# second: fixing params for neg gaussian - applied on individual frames. returns recentered array, and x-y shifts             
#                tmp_tmp, sy, sx = cube_recenter_2dfit(tmp_tmp, xy=true_agpm_cen, 
#			                                        fwhm=self.fwhm, subi_size=subi_size, 
#			                                        model=model, nproc=nproc, imlib='opencv', 
#			                                        interpolation='lanczos4',
#			                                        offset=None, negative=False, 
#			                                        threshold=True, sigfactor=sigfactor, 
#			                                        fix_neg=True, params_2g=params_2g,
#			                                        save_shifts=False, full_output=True, 
#			                                        verbose=verbose, debug=debug, plot=plot)		
        # LOAD IN REAL_NDIT_SCI
        # Load original cubes, shift them, and create master cube
        if crop_sz is not None:
            crop = True
            if not crop_sz % 2:
                crop_sz -= 1
                print('Crop size not odd, adapted to {}'.format(crop_sz), flush=True)
            print('Cropping to {} pixels'.format(crop_sz), flush=True)
            tmp_tmp = np.zeros([int(np.sum(self.real_ndit_sci)), crop_sz, crop_sz])
        else:
            tmp_tmp = np.zeros([int(np.sum(self.real_ndit_sci)), ny, nx])

        angles_1dvector = np.zeros([int(np.sum(self.real_ndit_sci))])  # empty array for derot angles, length of number of frames
        if verbose:
            print('Shifting frames and creating master science cube', flush=True)
        for sc, fits_name in enumerate(self.sci_list):
            tmp = open_fits(self.inpath+'4_sky_subtr_imlib_'+fits_name, verbose=debug)  # opens science cube
            if crop:
                tmp = cube_crop_frames(tmp, crop_sz, force=False, verbose=debug, full_output=False)
            dim = int(self.real_ndit_sci[sc])  # gets the integer dimensions of this science cube
            for dd in range(dim):  # dd goes from 0 to the largest dimension
                tmp_tmp[int(np.sum(self.real_ndit_sci[:sc]))+dd] = frame_shift(tmp[dd], shift_y=sy[sc], shift_x=sx[sc], imlib='opencv')  # this line applies the shifts to all the science images in the cube the loop is currently on. it also converts all cubes to a single long cube by adding the first dd frames, then the next dd frames from the next cube and so on
                angles_1dvector[int(np.sum(self.real_ndit_sci[:sc]))+dd] = self.derot_angles_cropped[sc][dd]  # turn 2d rotation file into a vector here same as for the mastercube above
                # sc*ndit+dd i don't think this line works for variable sized cubes
            if debug:
                get_available_memory()
                print('Science cube number: {}'.format(sc+1), flush=True)

        # write all the shifts
        write_fits(self.outpath+'x_shifts.fits', sx, verbose=debug)  # writes the x shifts to the file
        write_fits(self.outpath+'y_shifts.fits', sy, verbose=debug)  # writes the y shifts to the file
        write_fits(self.outpath+'{}_master_cube.fits'.format(self.dataset_dict['source']), tmp_tmp, verbose=debug)  # makes the master cube
        write_fits(self.outpath+'derot_angles.fits', angles_1dvector, verbose=debug)  # writes the 1D array of derotation angles
        if verbose:
            print('Shifts applied, master cube saved', flush=True)
        del tmp_tmp, sx, sy, angles_1dvector

    def bad_frame_removal(self, pxl_shift_thres=0.5, sub_frame_sz=31, verbose=True, debug=False, plot=True):
        """
        For removing outlier frames often caused by AO errors. To be run after recentring is complete. Takes the
        recentred mastercube and removes frames with a shift greater than a user defined pixel threshold in x or y above
        the median shift. It then takes the median of those cubes and correlates them to the median combined mastercube.
        Removes all those frames below the threshold from the mastercube and rotation file, then saves both as new files
        for use in post processing

        Parameters:
        ----------
        pxl_shift_thres : float, in units of pixels. Default is 0.5 pixels.
            Any shifts in the x or y direction greater than this threshold will cause the frame/s
            to be labelled as bad and thus removed. May required a stricter threshold depending on the dataset
        sub_frame_sz : integer, must be odd. Default is 31.
            This sets the cropping during frame correlation to the median
        debug : bool
            Will show open and save messages for FITS files
        plot : bool
            Will write the correlation plot to file if True, False will not
        """

        if verbose:
            print('######### Beginning bad frame removal #########', flush=True)

        if not sub_frame_sz % 2:
            sub_frame_sz -= 1
            print('WARNING: Bad frame sub image size not odd. Adjusted to {} px'.format(sub_frame_sz))

        angle_file = open_fits(self.outpath+'derot_angles.fits', verbose=debug)  # opens the rotation file
        recentered_cube = open_fits(self.outpath+'{}_master_cube.fits'.format(self.dataset_dict['source']), verbose=debug)  # loads the master cube

        # open x shifts file for the respective method
        x_shifts = open_fits(self.outpath+"x_shifts.fits", verbose=debug)
        median_sx = np.median(x_shifts)  # median of x shifts

        # opens y shifts file for the respective method
        y_shifts = open_fits(self.outpath+"y_shifts.fits", verbose=debug)
        median_sy = np.median(y_shifts)  # median of y shifts

        # self.ndit came from the z dimension of the first calibrated science cube above in recentring
        # x_shifts_long = np.zeros([len(self.sci_list)*self.ndit]) # list with number of cubes times number of frames in each cube as the length
        # y_shifts_long = np.zeros([len(self.sci_list)*self.ndit])
        if not self.fast_reduction:  # long are shifts to be apply to each frame in each cube. fast reduction only has one cube
            x_shifts_long = np.zeros([int(np.sum(self.real_ndit_sci))])
            y_shifts_long = np.zeros([int(np.sum(self.real_ndit_sci))])

            for i in range(len(self.sci_list)):  # from 0 to the length of sci_list
                ndit = self.real_ndit_sci[i]  # gets the dimensions of the cube
                x_shifts_long[i*ndit:(i+1)*ndit] = x_shifts[i]  # sets the average shifts of all frames in that cube
                y_shifts_long[i*ndit:(i+1)*ndit] = y_shifts[i]

            write_fits(self.outpath+'x_shifts_long.fits', x_shifts_long, verbose=debug)  # saves shifts to file
            write_fits(self.outpath+'y_shifts_long.fits', y_shifts_long, verbose=debug)
            x_shifts = x_shifts_long
            y_shifts = y_shifts_long

        if verbose:
            print("x shift median:", median_sx)
            print("y shift median:", median_sy)

        bad = []
        good = []

        i = 0 
        shifts = list(zip(x_shifts,y_shifts))
        bar = pyprind.ProgBar(len(x_shifts), stream=1, title='Running pixel shift check...')
        for sx, sy in shifts:  # iterate over the shifts to find any greater or less than pxl_shift_thres pixels from median
            if abs(sx) < ((abs(median_sx)) + pxl_shift_thres) and abs(sx) > ((abs(median_sx)) - pxl_shift_thres) and abs(sy) < ((abs(median_sy)) + pxl_shift_thres) and abs(sy) > ((abs(median_sy)) - pxl_shift_thres):
                good.append(i)
            else:   		
                bad.append(i)
            i += 1
            bar.update()

        # only keeps the files that weren't shifted above the threshold
        frames_pxl_threshold = recentered_cube[good]
        # only keeps the corresponding derotation entry for the frames that were kept
        angle_pxl_threshold = angle_file[good]
        del recentered_cube, angle_file

        if verbose:
            print('Frames within pixel shift threshold:', len(frames_pxl_threshold))
            print('########### Median combining {} frames for correlation check... ###########'.format(
                len(frames_pxl_threshold)))

        # makes array of good frames from the recentered mastercube
        subarray = cube_crop_frames(frames_pxl_threshold, size=sub_frame_sz, verbose=verbose)  # crops all the frames to a common size
        frame_ref = np.nanmedian(subarray, axis=0)  # median frame of remaining cropped frames, can be sped up with multi-processing

        if verbose:
            print('Running frame correlation check...')

        # calculates correlation threshold using the median of the Pearson correlation of all frames, minus 1 standard deviation 

        # frame_ref = frame_crop(tmp_median, size = sub_frame_sz, verbose=verbose) # crops the median of all frames to a common size
        distances = cube_distance(subarray, frame_ref, mode='full', dist='pearson', plot=plot)  # calculates the correlation of each frame to the median and saves as a list
        if plot:  # save a plot of distances compared to the median for each frame if set to 'save'
            plt.savefig(self.outpath+'distances.pdf', format='pdf')
            plt.close('all')
        correlation_thres = np.median(distances) - np.std(distances)  # threshold is the median of the distances minus one stddev
        
        good_frames, bad_frames = cube_detect_badfr_correlation(subarray,
                                                                frame_ref=frame_ref,
                                                                dist='pearson',
                                                                threshold=correlation_thres,
                                                                plot=plot,
                                                                verbose=verbose)
        if plot:
            plt.savefig(self.outpath+'frame_correlation.pdf', format='pdf')
            plt.close('all')

        # only keeps the files that were above the correlation threshold
        frames_threshold = frames_pxl_threshold[good_frames]
        del frames_pxl_threshold
        if verbose:
            print('Frames within correlation threshold:', len(frames_threshold))
        # only keeps the derotation entries for the good frames above the correlation threshold     
        angle_threshold = angle_pxl_threshold[good_frames]

        # saves the good frames to a new file, and saves the derotation angles to a new file
        write_fits(self.outpath+'{}_master_cube.fits'.format(self.dataset_dict['source']), frames_threshold,
                   verbose=debug)
        write_fits(self.outpath+'derot_angles.fits', angle_threshold, verbose=debug)
        if verbose: 
            print('Saved good frames and their respective rotations to file', flush=True)
        del frames_threshold

    def crop_cube(self, arcsecond_diameter=3, verbose=True, debug=False):
    
        """
        Crops frames in the master cube after recentring and bad frame removal. Recommended for post-processing ie.
        PCA in concentric annuli. If the provided arcsecond diameter happens to be larger than the cropping provided in
        recentring, no cropping will occur.

        Parameters
        ----------
        arcsecond_diameter : float or int
            Size of the frames diameter in arcseconds. Default of 3" for NaCO corresponds to 111x111 (x,y) pixel frames.
            Note this is a diameter, not a radius.
        verbose : bool optional
            If True extra messages of completion are shown.
        debug : bool
            Prints extra information during cropping, and when FITS are opened or saved.

        Writes to FITS file
        -------
        cropped cube : numpy ndarray
            Cube with cropped frames
        """
        if not isfile(self.outpath+'{}_master_cube.fits'.format(self.dataset_dict['source'])):
            raise NameError('Missing master cube from recentring and bad frame removal!')

        master_cube = open_fits(self.outpath+'{}_master_cube.fits'.format(self.dataset_dict['source']),
                                verbose=debug)
        _, ny, _ = master_cube.shape
        crop_size = int(np.ceil(arcsecond_diameter / self.dataset_dict['pixel_scale']))  # rounds up

        if not crop_size % 2:
            crop_size += 1
            print('Crop size not odd, increased to {}'.format(crop_size))
        if debug:
            print('Input crop size is {} pixels'.format(crop_size))

        if crop_size >= ny:
            print('Crop size is larger than the frame size. Skipping cropping...', flush=True)

        else:
            if verbose:
                print('######### Running frame cropping #########', flush=True)
                start_time = time_ini(verbose=False)
            master_cube = cube_crop_frames(master_cube, crop_size, force=False, verbose=debug, full_output=False)
            if verbose:
                timing(start_time)
                print('Cropping complete', flush=True)
            write_fits(self.outpath + '{}_master_cube.fits'.format(self.dataset_dict['source']), master_cube,
                       verbose=debug)
        del master_cube

    def median_binning(self, binning_factor=10, verbose=True, debug=False):
        """ 
        Median combines the frames within the master science cube as per the binning factor, and makes the necessary
        changes to the derotation file.
        
        Parameters:
        ----------
        binning_factor: int, default = 10
            Defines how many frames to median combine
                  
        Writes to FITS file:
        ----------
        the binned master cube
        the binned derotation angles
        """

        if not isinstance(binning_factor, int) and not isinstance(binning_factor, list) and \
                not isinstance(binning_factor, tuple):  # if it isn't int, tuple or list then raise an error
            raise TypeError('Invalid binning_factor! Use either int, list or tuple')        
        
        if not isfile(self.outpath+'{}_master_cube.fits'.format(self.dataset_dict['source'])):
            raise NameError('Missing master cube from recentring and bad frame removal!')
            
        if not isfile(self.outpath+'derot_angles.fits'):
            raise NameError('Missing derotation angles files from recentring and bad frame removal!')

        master_cube = open_fits(self.outpath+'{}_master_cube.fits'.format(self.dataset_dict['source']), verbose=debug)
        derot_angles = open_fits(self.outpath+'derot_angles.fits', verbose=debug)

        if verbose:
            start_time = time_ini(verbose=False)

        ntot = master_cube.shape[0]
        if binning_factor != 1 and binning_factor != 0:
            bin_fac = int(binning_factor)  # ensure integer
            ntot_bin = int(np.ceil(ntot / bin_fac))  # in case ntot is not divisible by the binning factor
            cube_bin = np.zeros([ntot_bin, master_cube.shape[1], master_cube.shape[2]])  # define empty array
            derot_angles_bin = np.zeros(ntot_bin)
            if verbose:
                print('Median binning master cube with binning factor {}'.format(bin_fac), flush=True)
            for nn in range(ntot_bin):  # median binning
                cube_bin[nn] = np.nanmedian(master_cube[nn * bin_fac:(nn + 1) * bin_fac], axis=0)
                derot_angles_bin[nn] = np.median(derot_angles[nn * bin_fac:(nn + 1) * bin_fac])
            write_fits(self.outpath+'{}_master_cube.fits'.format(self.dataset_dict['source']), cube_bin,
                       verbose=debug)
            write_fits(self.outpath+'derot_angles.fits', derot_angles_bin, verbose=debug)
        else:
            print('Binning factor is {}, skipping binning...'.format(binning_factor), flush=True)
        if verbose:
            print('Binning complete', flush=True)
        if verbose:
            timing(start_time)  # prints how long median binning took
        del master_cube, cube_bin, derot_angles, derot_angles_bin  # memory management
