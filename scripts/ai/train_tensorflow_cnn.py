#!/usr/bin/env python3
"""Train, evaluate, and save the temporal side-channel CNN."""
from __future__ import annotations
import argparse,json,random
from pathlib import Path
import numpy as np
from dataset import load_dataset
def main():
 p=argparse.ArgumentParser(); p.add_argument('--dataset',type=Path,required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--epochs',type=int,default=50); p.add_argument('--batch-size',type=int,default=64); p.add_argument('--seed',type=int,default=42); a=p.parse_args()
 import tensorflow as tf
 random.seed(a.seed); np.random.seed(a.seed); tf.random.set_seed(a.seed)
 _,seq,y=load_dataset(a.dataset); idx=np.arange(len(y)); np.random.shuffle(idx); split=int(.8*len(y)); tr,va=idx[:split],idx[split:]
 classes=int(y.max()+1)
 inputs=tf.keras.Input(shape=seq.shape[1:]); x=tf.keras.layers.Conv1D(32,7,padding='same',activation='relu')(inputs); x=tf.keras.layers.BatchNormalization()(x); x=tf.keras.layers.MaxPool1D(2)(x); x=tf.keras.layers.Conv1D(64,5,padding='same',activation='relu')(x); x=tf.keras.layers.BatchNormalization()(x); x=tf.keras.layers.GlobalAveragePooling1D()(x); x=tf.keras.layers.Dropout(.25)(x); outputs=tf.keras.layers.Dense(classes,activation='softmax')(x)
 model=tf.keras.Model(inputs,outputs); model.compile(optimizer=tf.keras.optimizers.Adam(1e-3),loss='sparse_categorical_crossentropy',metrics=['accuracy'])
 callbacks=[tf.keras.callbacks.EarlyStopping(patience=8,restore_best_weights=True,monitor='val_loss'),tf.keras.callbacks.ReduceLROnPlateau(patience=4,factor=.5)]
 h=model.fit(seq[tr],y[tr],validation_data=(seq[va],y[va]),epochs=a.epochs,batch_size=a.batch_size,callbacks=callbacks,verbose=2)
 a.output.parent.mkdir(parents=True,exist_ok=True); model.save(a.output); metrics=model.evaluate(seq[va],y[va],verbose=0,return_dict=True); a.output.with_suffix('.metrics.json').write_text(json.dumps({"metrics":metrics,"history":h.history},indent=2,default=float))
if __name__=='__main__': main()
