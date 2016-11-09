from __future__ import print_function
import tensorflow as tf
slim = tf.contrib.slim


import eegnet_v1 as network
import read_preproc_dataset as read

##
# Directories
#

tf.app.flags.DEFINE_string('dataset_dir', '/shared/dataset/train/*', 
    'Where dataset TFReaders files are loaded from.')

tf.app.flags.DEFINE_string('log_dir', '/shared/logs/',
    'Where checkpoints and event logs are written to.')

##
# TFReaders configuration
##

tf.app.flags.DEFINE_integer('file_num_points', 240000,
                            'Data points in each TFReader file.')

tf.app.flags.DEFINE_integer('file_num_channels', 16,
                            'Sensor channels in each TFReader file.')

tf.app.flags.DEFINE_integer('file_num_splits', 1,
                            'Splits to perform on each TFReader file.')

tf.app.flags.DEFINE_boolean('file_remove_dropouts', True,
                            'Remove or Not dropouts from input data.')

tf.app.flags.DEFINE_float('sigma_threshold', 0.5,
                          'Standard deviation threshold under which file is considered dropout.')

tf.app.flags.DEFINE_integer('batch_size', 16,
                            'Number of splits/files in each batch to the network.')

##
# Network configuration
##

tf.app.flags.DEFINE_integer('num_labels', 2,
                            'Labels/classes being classified. 0 - Interictal | 1 - Preictal')

tf.app.flags.DEFINE_integer('filter_width', 3,
                            'Convolutional filter width.')

tf.app.flags.DEFINE_integer('residual_channels', 3*16,
                            'Output channels of input convolution layer and residual paths.')

tf.app.flags.DEFINE_integer('pool_size', 2400,
                            'Data points after pooling layer. New value requires new fully_connected weights.')


FLAGS = tf.app.flags.FLAGS


def get_init_fn():
    checkpoint_path = tf.train.latest_checkpoint(FLAGS.log_dir)
    
    if checkpoint_path is None:
        tf.logging.info('No checkpoint found in %s' % FLAGS.log_dir)
        return None
    
    tf.logging.info('Loading model from %s' % checkpoint_path)
    
    variables_to_restore = slim.get_model_variables()
    
    ## Create dictionary between old names and new ones
    #name_in_checkpoint = lambda var: var.op.name.replace("eegnet_v1", "eegnet_network")    
    #variables_to_restore = {name_in_checkpoint(var):var for var in variables_to_restore}
    
    return slim.assign_from_checkpoint_fn(
        checkpoint_path, 
        variables_to_restore, 
        ignore_missing_vars=True,
    )


def main(_):
    tf.logging.set_verbosity(tf.logging.INFO)
    with tf.Graph().as_default():
        # Input pipeline
        train_data, train_labels = read.read_dataset(tf.gfile.Glob(FLAGS.dataset_dir), 
                                                     num_points=FLAGS.file_num_points,
                                                     num_channels=FLAGS.file_num_channels,
                                                     num_labels=FLAGS.num_labels,
                                                     num_splits=FLAGS.file_num_splits,
                                                     sigma_threshold=FLAGS.sigma_threshold,
                                                     batch_size=FLAGS.batch_size)
        shape = train_data.get_shape().as_list()
        tf.logging.info('Batch size/num_points: %d/%d' % (shape[0], shape[2]))
        
        # Create model   
        logits = network.eegnet_v1(train_data,
                                   num_labels=FLAGS.num_labels,
                                   filter_width=FLAGS.filter_width,
                                   residual_channels=FLAGS.residual_channels,
                                   pool_size=FLAGS.pool_size,
                                   is_training=True)
        tf.logging.info('Network model created.')

        # Add histograms for trainable variables.
        for var in tf.trainable_variables():
            tf.histogram_summary(var.op.name, var)

        # Add summaries for activations: NOT WORKING YET. TF ERROR.
        #slim.summarize_activations()

        # Specify loss
        slim.losses.softmax_cross_entropy(logits, train_labels, scope='loss')
        total_loss = slim.losses.get_total_loss()
        # Summarize loss
        tf.scalar_summary('losses/Total loss', total_loss)

        # Optimizer and training op
        optimizer = tf.train.AdamOptimizer(learning_rate=1e-3, epsilon=1e-4)
        train_op = slim.learning.create_train_op(total_loss, optimizer)

        # Train accuracy
        train_probabilities = tf.nn.softmax(logits)
        train_predictions = tf.one_hot(tf.argmax(train_probabilities, 1), FLAGS.num_labels, dtype=tf.int32)
        train_accuracy = slim.metrics.accuracy(train_predictions, train_labels, 100.0)
        # Summarize train accuracy
        tf.scalar_summary('accuracy/Train accuracy', train_accuracy)

        # Run the training
        final_loss = slim.learning.train(
            train_op, 
            logdir=FLAGS.log_dir, 
            log_every_n_steps=1, 
            is_chief=True, 
            number_of_steps=25001, 
            init_fn=get_init_fn(), 
            save_summaries_secs=300, 
            save_interval_secs=2*3600, 
            trace_every_n_steps=3600, 
        )
    
    
if __name__ == '__main__':
    tf.app.run()