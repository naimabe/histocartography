"""Tumor Slide Classification ."""
import logging
import sys
import numpy as np

import tensorflow as tf
from keras.preprocessing.image import ImageDataGenerator
from keras.models import load_model
from keras.models import model_from_json

# setup logging

#logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
log = logging.getLogger('Histocartography::ML::Tumor Slide Prediction')
h1 = logging.StreamHandler(sys.stdout)
log.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
h1.setFormatter(formatter)
log.addHandler(h1)


def predict_for_image(patch_info_coordinates, image=None, model_json=None, model_weights=None, visualize=1):
    all_patches = []
    print('image shape : ', image.shape)
    for i, loc in enumerate(patch_info_coordinates):
        patch_image = image[loc[1]: loc[3], loc[2]:loc[4], :]
        all_patches.append(patch_image)

    all_patches = np.array(all_patches)
    log.info('n_patches : {}'.format(all_patches.shape))

    batch_size = 32
    json_file = open(model_json, 'r')
    loaded_model_json = json_file.read()
    json_file.close()
    model = model_from_json(loaded_model_json)
    model.load_weights(model_weights)
    log.info('Model loaded')

    datagen = ImageDataGenerator(rescale=1. / 255)
    datagen.fit(all_patches)
    n_steps = np.ceil(len(all_patches) / batch_size)
    y_pred_prob = model.predict_generator(datagen.flow(all_patches, batch_size=batch_size), steps=n_steps)
    y_pred = np.argmax(y_pred_prob, axis=1)

    log.info('len y_pred_prob : {}'.format(len(y_pred_prob)))
    log.info('Eg. y_pred_prob : {}'.format(y_pred_prob[0:10]))
    y_pred_0 = np.count_nonzero(y_pred==0)
    y_pred_1 = np.count_nonzero(y_pred==1)
    n_classes = [y_pred_0, y_pred_1]
    log.info('n_nroi_roi: {}'.format(n_classes))

    return y_pred




