#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Apr 12 13:11:12 2020

@author: lewis, iain
"""
#classification stage already completed

from naco_pip import input_dataset, raw_dataset, calib_dataset

clas = input_dataset('/home/ihammond/pd87_scratch/products/NACO_archive/5_HD179218/raw/','/home/ihammond/pd87_scratch/products/IainData/HD179218/classified/')

clas.bad_columns()
clas.mk_dico()
clas.find_sky_in_sci_cube(plot = 'save')
clas.find_derot_angles()

calib = raw_dataset('/home/ihammond/pd87_scratch/products/IainData/HD179218/classified/','/home/ihammond/pd87_scratch/products/IainData/HD179218/calibrated')

calib.dark_subtract(debug = False, plot = False)
calib.flat_field_correction(debug = False, plot = False)
calib.correct_nan(debug = False, plot = False)
calib.correct_bad_pixels(debug = False, plot = False)
calib.first_frames_removal(debug = False, plot = False)
calib.get_stellar_psf(debug = False, plot = False)
calib.subtract_sky(debug = False, plot = False)

preproc = calib_dataset('/home/ihammond/pd87_scratch/products/IainData/HD179218/calibrated','/home/ihammond/pd87_scratch/products/IainData/HD179218/preprocessed/',47,calib.fwhm,coro=True)

preproc.recenter(method = '2dfit',model = '2gauss',nproc = 8, sigfactor = 4, subi_size = 21,verbose = True, debug = False, plot = False, coro = True)
preproc.bad_frame_removal(recenter_method = '2dfit', recenter_model = '2gauss',correlation_thres = 0.90, pxl_shift_thres = 0.5, crop_size = 31, verbose = True, debug = False, plot = False)