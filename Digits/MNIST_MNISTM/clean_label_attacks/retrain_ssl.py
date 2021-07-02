import sys
sys.path.append("../")
import numpy as np
import tensorflow as tf
from utils import eval_accuracy_main_cdan
from models import mnist2mnistm_shared_CDAN, mnist2mnistm_softmax
import keras
import argparse
import pickle as pkl 
import tensorflow_addons as tfa

parser = argparse.ArgumentParser(description='Training', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--USE_POISON', type=int, default=1, help='POISON used or not')
args = parser.parse_args()
USE_POISON = bool(args.USE_POISON)
METHOD = "ssl"

IMG_WIDTH = 28
IMG_HEIGHT = 28
NCH = 3

NUM_CLASSES_MAIN = 2
NUM_CLASSES_AUX = 4
NUM_CLASSES_DC = 2

EPOCHS = 101
BATCH_SIZE = 64
PLOT_POINTS = 100

NUM_MODELS = 5

ce_loss = tf.keras.losses.CategoricalCrossentropy(from_logits=True)

shared = [mnist2mnistm_shared_CDAN([50000, IMG_HEIGHT, IMG_WIDTH, NCH])for i in range(NUM_MODELS)]

main_classifier = [mnist2mnistm_softmax(shared[i], NUM_CLASSES_MAIN, 500) for i in range(NUM_MODELS)]
aux_classifier = [mnist2mnistm_softmax(shared[i], NUM_CLASSES_AUX, 500) for i in range(NUM_MODELS)]

optimizer_shared = [tf.keras.optimizers.Adam(1E-3, beta_1=0.5) for i in range(NUM_MODELS)]

optimizer_main_classifier = [tf.keras.optimizers.Adam(1E-3, beta_1=0.5) for i in range(NUM_MODELS)]
optimizer_aux_classifier = [tf.keras.optimizers.Adam(1E-3, beta_1=0.5) for i in range(NUM_MODELS)]

@tf.function
def train_step_uda_ssl(main_data, main_labels, aux_data, aux_labels):
    # persistent is set to True because the tape is used more than
    # once to calculate the gradients.
    
    with tf.GradientTape(persistent=True) as tape:
        shared_main = [shared[i](main_data, training=True) for i in range(NUM_MODELS)]
        main_logits = [main_classifier[i](shared_main[i], training=True) for i in range(NUM_MODELS)]
        main_loss = [ce_loss(main_labels, main_logits[i]) for i in range(NUM_MODELS)]
        
        shared_aux = [shared[i](aux_data, training=True) for i in range(NUM_MODELS)]
        aux_logits = [aux_classifier[i](shared_aux[i], training=True) for i in range(NUM_MODELS)]
        aux_loss = [ce_loss(aux_labels, aux_logits[i]) for i in range(NUM_MODELS)]
        
        loss = [main_loss[i] + aux_loss[i] for i in range(NUM_MODELS)]
            
    gradients_shared = [tape.gradient(loss[i], shared[i].trainable_variables) for i in range(NUM_MODELS)]
    
    gradients_main_classifier = [tape.gradient(loss[i], main_classifier[i].trainable_variables) for i in range(NUM_MODELS)]
    gradients_aux_classifier = [tape.gradient(loss[i], aux_classifier[i].trainable_variables) for i in range(NUM_MODELS)]
    
    [optimizer_shared[i].apply_gradients(zip(gradients_shared[i], shared[i].trainable_variables))  for i in range(NUM_MODELS)]
    [optimizer_main_classifier[i].apply_gradients(zip(gradients_main_classifier[i], main_classifier[i].trainable_variables)) for i in range(NUM_MODELS)]
    [optimizer_aux_classifier[i].apply_gradients(zip(gradients_aux_classifier[i], aux_classifier[i].trainable_variables)) for i in range(NUM_MODELS)]
    
    return loss


mnist = tf.keras.datasets.mnist
(x_train_mnist_all, y_train_mnist_all), (x_test_mnist_all, y_test_mnist_all) = mnist.load_data()

x_train_mnist_all = np.stack((x_train_mnist_all,)*3, axis=-1)/255.
x_test_mnist_all = np.stack((x_test_mnist_all,)*3, axis=-1)/255.

mnistm = pkl.load(open('../../../../MNIST_MNIST-m/mnistm_data.pkl', 'rb'))
x_train_mnistm_all = mnistm['train']/255.
x_test_mnistm_all = mnistm['test']/255.

picked_class = 3
picked_class_next = 8

train_points_class_0 = np.argwhere(y_train_mnist_all == picked_class).flatten()
train_points_class_1 = np.argwhere(y_train_mnist_all == picked_class_next).flatten()

test_points_class_0 = np.argwhere(y_test_mnist_all == picked_class).flatten()
test_points_class_1 = np.argwhere(y_test_mnist_all == picked_class_next).flatten()
print(len(train_points_class_0), len(train_points_class_1), len(test_points_class_0), len(test_points_class_1))

x_train_mnist = x_train_mnist_all[np.concatenate([train_points_class_0, train_points_class_1])]
y_train_mnist = y_train_mnist_all[np.concatenate([train_points_class_0, train_points_class_1])]

x_test_mnist = x_test_mnist_all[np.concatenate([test_points_class_0, test_points_class_1])]
y_test_mnist = y_test_mnist_all[np.concatenate([test_points_class_0, test_points_class_1])]

x_train_mnistm = x_train_mnistm_all[np.concatenate([train_points_class_0, train_points_class_1])]
x_test_mnistm = x_test_mnistm_all[np.concatenate([test_points_class_0, test_points_class_1])]

zeros_train = np.argwhere(y_train_mnist == picked_class).flatten()
ones_train = np.argwhere(y_train_mnist == picked_class_next).flatten()
zeros_test = np.argwhere(y_test_mnist == picked_class).flatten()
ones_test = np.argwhere(y_test_mnist == picked_class_next).flatten()

y_train_mnist[zeros_train] = 0
y_train_mnist[ones_train] = 1
y_test_mnist[zeros_test] = 0
y_test_mnist[ones_test] = 1

y_train_mnist = keras.utils.to_categorical(y_train_mnist, NUM_CLASSES_MAIN)
y_test_mnist = keras.utils.to_categorical(y_test_mnist, NUM_CLASSES_MAIN)

x_target_test = np.load("data/" + METHOD + "_TARGET_DATA.npy")
y_target_test = np.load("data/" + METHOD + "_TARGET_LABEL.npy")
y_target_test_incorrect_label = np.zeros([1, NUM_CLASSES_MAIN])
target_correct_label = np.argmax(y_target_test,1).flatten()[0]
y_target_test_incorrect_label[0][(target_correct_label+1)%NUM_CLASSES_MAIN]=1

if USE_POISON:

    x_poison = np.load("data/" + METHOD + "_GENERATED_POISON_DATA.npy")
    y_poison = np.load("data/" + METHOD + "_GENERATED_POISON_LABELS.npy") 

    x_train_mnist = np.concatenate([x_train_mnist, x_poison])
    y_train_mnist = np.concatenate([y_train_mnist, y_poison])
    
for epoch in range(EPOCHS):
    nb_batches_train = int(len(x_train_mnist)/BATCH_SIZE)
    if len(x_train_mnist) % BATCH_SIZE != 0:
        nb_batches_train += 1
    ind_shuf = np.arange(len(x_train_mnist))
    np.random.shuffle(ind_shuf)
    
    for batch in range(nb_batches_train):
        ind_batch = range(BATCH_SIZE * batch, min(BATCH_SIZE * (1+batch), len(x_train_mnist)))
        ind_source = ind_shuf[ind_batch]
        
        x_source_batch = x_train_mnist[ind_source]
        y_source_batch = y_train_mnist[ind_source]
        
        ind_target = np.random.choice(len(x_train_mnistm), size=len(ind_source), replace=False)
        
        x_target_batch = x_train_mnistm[ind_target]
        
        x_aux_init = np.concatenate([x_source_batch, x_target_batch])
        y_aux_init = np.random.randint(0, NUM_CLASSES_AUX, len(x_aux_init))
        
        x_aux = tfa.image.rotate(x_aux_init, tf.cast(y_aux_init * (np.pi/2), tf.float32))
        y_aux = keras.utils.to_categorical(y_aux_init, NUM_CLASSES_AUX)
            
        loss = train_step_uda_ssl(x_source_batch, y_source_batch, x_aux, y_aux)
    
    if epoch % 20 == 0:  
        print("Full training Poisoning:", USE_POISON, "MNIST->MNIST_M:", epoch, "METHOD:", METHOD, "\n")
        print([eval_accuracy_main_cdan(x_target_test, y_target_test_incorrect_label, shared[i], main_classifier[i])  for i in range(NUM_MODELS)])
        print([eval_accuracy_main_cdan(x_target_test, y_target_test, shared[i], main_classifier[i]) for i in range(NUM_MODELS)])
        print([eval_accuracy_main_cdan(x_test_mnistm, y_test_mnist, shared[i], main_classifier[i]) for i in range(NUM_MODELS)])
        if USE_POISON:
            print([eval_accuracy_main_cdan(x_poison, y_poison, shared[i], main_classifier[i]) for i in range(NUM_MODELS)])
        print("\n")
        
