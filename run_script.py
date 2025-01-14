#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Apr 12 13:11:12 2020
@author: iain, lewis
"""
from naco_pip import input_dataset, raw_dataset, calib_dataset, preproc_dataset

# quick basic checks
import os
try:
    from vip_hci.config import get_available_memory
except:
    from vip_hci.conf import get_available_memory
    print('A newer version of VIP is available')

sep = '―' * 45  # used in printing functions
print('\n'+sep+'\n'+'Starting NaCo pipeline (Hammond et al. 2022)'+'\n'+sep+'\n')
try:
    nproc = int(os.getenv('SLURM_CPUS_PER_TASK', default=1))
except:
    nproc = 1
get_available_memory()
print('Number of CPUs: {} \n'.format(nproc), flush=True)

# VLT/NaCo info, doesn't need to be changed
wavelength = 3.78e-6  # meters
size_telescope = 8.2  # meters
pixel_scale = 0.027208  # arcsecs per pixel, Launhardt et al. 2020, +/- 0.0000088

# ***************************************** PARAMETERS TO CHANGE *******************************************************

# HD 169142
source = 'HD_169142'  # used in some saved filenames and plots, without spaces
details = '(NACO+AGPM)'  # info displayed in plots and figures
ndit_sci = [100]  # number of frames per science cube
ndit_sky = [100]  # number of frames per sky cube
ndit_unsat = [400]  # number of frames in unsaturated cubes
dit_sci = 0.35  # integration time for science frames
dit_unsat = 0.07  # integration time for unsaturated non coronagraphic images
dit_flat = 0.2  # integration time for flat frames
fast_reduction = False  # for super fast calibration and pre-processing (median combines all science cubes into one cube)

# Can be ignored. Dictionary to pass through the pipeline saving all the static dataset information.
dataset_dict = {'wavelength':wavelength,'size_telescope':size_telescope,'pixel_scale':pixel_scale, 'source': source,
                'details': details,'ndit_sci': ndit_sci, 'ndit_sky':ndit_sky,'ndit_unsat':ndit_unsat,'dit_sci':dit_sci,
                'dit_unsat':dit_unsat,'dit_unsat':dit_unsat,'dit_flat':dit_flat,'fast_reduction':fast_reduction}

# ************************* Activate various functions and set inpath + outpaths ***************************************

# clas = input_dataset('/home/ihammond/pd87_scratch/products/NACO_archive/13_HD169142/raw/',
#                      '/home/ihammond/pd87_scratch/products/NACO_archive/13_HD169142/classified/', dataset_dict,coro=True)
# clas.bad_columns(verbose=True, debug=False)
# clas.mk_dico()
# clas.find_sky_in_sci_cube(plot='save')
# clas.find_derot_angles()

calib = raw_dataset('/home/ihammond/pd87_scratch/products/NACO_archive/13_HD169142/classified/',
                    '/home/ihammond/pd87_scratch/products/NACO_archive/13_HD169142/calibrated/', dataset_dict,final_sz=None)
calib.dark_subtract(method='median', bad_quadrant=[3], debug=False, plot='save')
calib.flat_field_correction(debug=False, plot='save')
calib.correct_nan(debug=False, plot='save')
calib.correct_bad_pixels(verbose=True, debug=False, plot='save')
calib.first_frames_removal(verbose=True, debug=False, plot='save')
calib.get_stellar_psf(nd_filter=False, debug=False, plot='save')
calib.subtract_sky(npc=1, debug=False, plot='save')

preproc = calib_dataset('/home/ihammond/pd87_scratch/products/NACO_archive/10_CQTau/calibrated/',
                        '/home/ihammond/pd87_scratch/products/NACO_archive/10_CQTau/preproc/', dataset_dict,
                        recenter_method='speckle', recenter_model='gauss', coro=True)
preproc.recenter(nproc=nproc, sigfactor=4, subi_size=41, crop_sz=251, verbose=True, debug=False, plot=True, coro=True)
preproc.bad_frame_removal(pxl_shift_thres=0.4, sub_frame_sz=31, verbose=True, debug=False, plot=True)
preproc.crop_cube(arcsecond_diameter=3, verbose=True, debug=False)  # required for PCA-ADI annular and contrast curves
preproc.median_binning(binning_factor=1, verbose=True)  # speeds up PCA-ADI annular and contrast curves, reduces S/N

# postproc = preproc_dataset('/home/ihammond/pd87_scratch/products/NACO_archive/10_CQTau/preproc/',
#                             '/home/ihammond/pd87_scratch/products/NACO_archive/10_CQTau/postproc_nobin/',
#                            dataset_dict, nproc=nproc, npc=20) # npc can be int (for a single number of PCs), tuple
#                                                               # or list for a range and step
# postproc.postprocessing(do_adi=True, do_adi_contrast=True, do_pca_full=True, do_pca_ann=True, fake_planet=True,
#                         first_guess_skip=True, fcp_pos=[0.3], firstguess_pcs=[1, 5, 1], cropped=True, do_snr_map=False,
#                         do_snr_map_opt=False, planet_pos=None, delta_rot=(0.5, 3), mask_IWA=1, overwrite=True,
#                         verbose=True, debug=False)

# only to be run if there is a source/blob detected by running post-processing
# postproc.do_negfc(do_firstguess=True, guess_xy=[(63,56)], mcmc_negfc=True, inject_neg=True, ncomp=20,
#                   algo='pca_annular', nwalkers_ini=120, niteration_min = 25, niteration_limit=10000, delta_rot=(0.5,3),
#                   weights=False, coronagraph=False, overwrite=True, save_plot=True, verbose=True)

# some previous data sets:

# MWC480
# source = 'MWC480' # used in some saved filenames and plots
# details = '(NACO+AGPM)' # info displayed in plots and figures
# ndit_sci = [100] #number of frames per science cube
# ndit_sky = [100] # number of frames per sky cube
# ndit_unsat = [400] #number of frames in unsaturated cubes
# dit_sci = 0.35 #integration time for science frames in seconds
# dit_unsat = 0.05 #integration time for unsaturated non coronagraphic images in seconds
# dit_flat = 0.2 #integration time for flat frames in seconds
# fast_reduction = False # for super fast calibration and pre-processing (median combines all science cubes into one cube)

# HD179218
#source = 'HD179218' # used in some saved filenames and plots
#details = '(NACO+AGPM)' # info displayed in plots and figures
#dit_sci = 0.35 #integration time for sci
#ndit_sci = [100] #number of frames per cube
#ndit_sky = [100] # number of frames per sky cube
#dit_unsat = 0.07 #integration time for unsaturated non coronagraphic images
#ndit_unsat = [400] #number of unsaturated frames in cubes

# HD206893
# source = 'HD206893' # used in some saved filenames and plots
# details = '(NACO+AGPM)' # info displayed in plots and figures
# ndit_sci = [200] #number of frames per science cube
# ndit_sky = [50] # number of frames per sky cube
# ndit_unsat = [100] #number of frames in unsaturated cubes
# dit_sci = 0.3 #integration time for science frames
# dit_unsat = 0.1 #integration time for unsaturated non coronagraphic images
# dit_flat = 0.2 #integration time for flat frames

# CQTau
# source = 'CQTau'  # used in some saved filenames and plots, without spaces
# details = '(NACO+AGPM)'  # info displayed in plots and figures
# ndit_sci = [100]  # number of frames per science cube
# ndit_sky = [100]  # number of frames per sky cube
# ndit_unsat = [500, 400]  # number of frames in unsaturated cubes
# dit_sci = 0.35  # integration time for science frames
# dit_unsat = 0.05  # integration time for unsaturated non coronagraphic images
# dit_flat = 0.2  # integration time for flat frames
# fast_reduction = False  # for super fast calibration and pre-processing (median combines all science cubes into one cube)