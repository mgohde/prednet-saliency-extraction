#!/usr/bin/env python

# model.py -- This module implements a flexible model for saliency generation utilizing prednet.

import os
import sys
import numpy as np
from six.moves import cPickle
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from keras import backend as K
from keras.models import Model, model_from_json
from keras.layers import Input, Dense, Flatten

from prednet import PredNet
from data_utils import SequenceGenerator
from data_utils import PreloadedSequence
from kitti_settings import *
import hickle
from scipy import misc
import pysaliency
from scipy.ndimage import zoom
from scipy.misc import logsumexp

class PredSaliencyModel:# (pysaliency.SaliencyMapModel):
    
    def __init__(self, weightsfile, prior):
        #self.weights=hickle.load(weightsfile)
        
        # Load PredNet configuration and instantiate a prednet object:
        weights_file = os.path.join(WEIGHTS_DIR, 'prednet_kitti_weights.hdf5')
        json_file = os.path.join(WEIGHTS_DIR, 'prednet_kitti_model.json')
        
        # Load trained model
        f = open(json_file, 'r')
        json_string = f.read()
        f.close()
        train_model = model_from_json(json_string, custom_objects = {'PredNet': PredNet})
        train_model.load_weights(weights_file)
        
        # We have a pretrained model now. 
        layer_config=train_model.layers[1].get_config()
        layer_config['output_mode']='error'
        self.layer="E0"
        self.input_shape=list(train_model.layers[0].batch_input_shape[1:])
        # NOTE: We need to remember to set the input shape at 0 to the number of images in the series.
        self.prior=hickle.load(prior)
        self.data_format=layer_config['data_format'] if 'data_format' in layer_config else layer_config['dim_ordering']
        self.test_prednet=PredNet(weights=train_model.layers[1].get_weights(), **layer_config)
        
        
    
    # This will return a saliency map based on the input stimulus. 
    def predict(self, stimarray):
        # Determine the actual dimensions of the stimulus array:
        inputdims=(float(stimarray.shape[1]), float(stimarray.shape[2])) # Stimulus array dimensions are nelements, x, y, nchannels. Note that x and y may actually be reversed. (height, then width?)
        # Note that the prior should actually be scaled by the output shape, not the input shape...
        print("Stimulus array shape:")
        print(stimarray.shape)
        pshape=self.prior.shape
        print("Self prior shape:")
        print(pshape)
        print("Scaling factor:")
        print(inputdims)
        print((inputdims[0]/pshape[0], inputdims[1]/pshape[1]))
        prior=zoom(self.prior, (inputdims[0]/pshape[0], inputdims[1]/pshape[1]), order=0, mode="nearest")
        # Normalize?
        prior-=logsumexp(prior)
        
        nt=stimarray.shape[0]
        batch_size=min(nt, 100)
        self.input_shape[0]=nt
        inputs=Input(shape=tuple(self.input_shape))
        predictions=self.test_prednet(inputs)
        test_model=Model(inputs=inputs, outputs=predictions)
        test_generator=PreloadedSequence(stimarray, nt, sequence_start_mode="unique", data_format=self.data_format)
        
        print("Testing set:")
        Xtest=test_generator.create_all()
        print(Xtest)
        print("Predicting...")
        #ASSUMPTION: it is safe to set the batch size equal to the number of inputs here since we won't be dealing with many inputs. 
        predictions=test_model.predict(Xtest, batch_size)
        print("Shape of outputs:")
        
        # Now that we have a set of errors, let's do stuff:
        predictions=predictions[0] # Now the first index will be the image, then channels, then pixels.
        for i in range(predictions.shape[0]): # For each prediction:
            predictions[i]=predictions[i].sum(axis=0) # Sum all channels
            predictions[i]=predictions[i]*prior # Scale by resized prior distribution.
        return predictions
        
        