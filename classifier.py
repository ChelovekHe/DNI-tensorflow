import tensorflow as tf
import numpy as np
import math
import os
from utils import linear, unpickle, conv2d, pooling
from tensorflow.contrib.layers.python.layers import initializers

class mlp():

	def __init__(self, sess, dataset, conf, num_train=50000, input_size=3072, test_filename='/data2/andrewliao11/cifar-10-batches-py/test_batch'):

		self.sess = sess
		self.test_filename = test_filename
		self.w = 32
		self.h = 32
		self.channel = 3
		self.optim_type = conf.optim_type
		self.test_per_iter = conf.test_per_iter
		self.max_step = conf.max_step
		self.ckpt_dir = conf.checkpoint_dir
		self.batch_size = conf.batch_size
		self.num_train = num_train
		self.max_epoch = math.floor(conf.max_step/math.floor(self.num_train/self.batch_size))
		self.input_dims = input_size
		self.hidden_size = conf.hidden_size
		self.weight_initializer = initializers.xavier_initializer()
		self.bias_initializer = tf.constant_initializer(0.1)
		self.output_size = conf.output_size
		self.max_to_keep = conf.max_to_keep
		self.dataset = dataset
		self.var = {}

		self.global_step = tf.get_variable('global_step', [],initializer=tf.constant_initializer(0), trainable=False)
		if self.optim_type == 'exp_decay':
			decay_steps = int(math.floor(self.num_train/self.batch_size)* conf.num_epoch_per_decay)
			self.lr = tf.train.exponential_decay(conf.init_lr,
							self.global_step, decay_steps,
							conf.decay_factor,
							staircase=True)
			self.optim = tf.train.GradientDescentOptimizer(self.lr)
		elif self.optim_type == 'adam':
			self.optim = tf.train.AdamOptimizer(conf.init_lr)	

	def build_mlp_model(self):
		
		self.imgs = tf.placeholder('float32',[self.batch_size, self.input_dims])

		self.h1, self.var['l1_w'], self.var['l1_b'] = linear(self.imgs, self.hidden_size, 
							self.weight_initializer, self.bias_initializer, activation_fn=tf.nn.relu, name='l1_linear')
		self.h2, self.var['l2_w'], self.var['l2_b'] = linear(self.h1, self.hidden_size,
							self.weight_initializer, self.bias_initializer, activation_fn=tf.nn.relu, name='l2_linear')
		self.h3, self.var['l3_w'], self.var['l3_b'] = linear(self.h2, self.hidden_size, 
							self.weight_initializer, self.bias_initializer, activation_fn=tf.nn.relu, name='l3_linear')
		self.out, self.var['l4_w'], self.var['l4_b'] = linear(self.h3, self.output_size, 
							self.weight_initializer, self.bias_initializer, activation_fn=tf.nn.relu, name='l4_linear')
		self.out_logit = tf.nn.softmax(self.out)
		self.out_argmax = tf.argmax(self.out_logit, 1)
		self.labels = tf.placeholder('int32', [self.batch_size])
		self.loss = tf.nn.sparse_softmax_cross_entropy_with_logits(self.out, self.labels)
		self.loss= tf.reduce_mean(self.loss)

	def build_cnn_model(self):
		
		self.imgs = tf.placeholder('float32', [self.batch_size, self.input_dims])
		self.img_reshape = tf.reshape(self.imgs, [self.batch_size, self.w, self.h, self.channel])	
		self.h1, self.var['l1_w'], self.var['l1_b'] = conv2d(self.img_reshape, 128, [5,5], [1,1],
									self.weight_initializer, self.bias_initializer, batch_norm=True, activation_fn=tf.nn.relu, name='l1_con2d')		
		self.h1 = pooling(self.h1, kernel_size=[3,3], stride=[1,1], type='max')

		self.h2, self.var['l2_w'], self.var['l2_b'] = conv2d(self.h1, 128, [5,5], [1,1],
									self.weight_initializer, self.bias_initializer, batch_norm=True, activation_fn=tf.nn.relu, name='l2_con2d')
		self.h2 = pooling(self.h2, kernel_size=[3,3], stride=[1,1], type='average')

		self.h3, self.var['l3_w'], self.var['l3_b'] = conv2d(self.h2, 128, [5,5], [1,1],
									self.weight_initializer, self.bias_initializer, batch_norm=True, activation_fn=tf.nn.relu, name='l3_con2d')
		self.h3 = pooling(self.h3, kernel_size=[3,3], stride=[1,1], type='average')
		self.h3 = tf.reshape(self.h3, [self.batch_size, -1])

		self.out, self.var['l4_w'], self.var['l4_b'] = linear(self.h3, self.output_size,
									self.weight_initializer, self.bias_initializer, activation_fn=tf.nn.relu, name='l4_linear')
		self.out_logit = tf.nn.softmax(self.out)
		self.out_argmax = tf.argmax(self.out_logit, 1)
		self.labels = tf.placeholder('int32', [self.batch_size])
		self.loss = tf.nn.sparse_softmax_cross_entropy_with_logits(self.out, self.labels)
		self.loss = tf.reduce_sum(self.loss)/self.batch_size

	def train(self):

		self.train_op = self.optim.minimize(self.loss, global_step=self.global_step)
		tf.initialize_all_variables().run()
		self.saver = tf.train.Saver(max_to_keep=self.max_to_keep)
		for epoch_idx in range(int(self.max_epoch)):
			for idx in range(int(math.floor(self.num_train/self.batch_size))):
				img_batch, label_batch = self.dataset.sequential_sample(self.batch_size)
				_, loss = self.sess.run([self.train_op, self.loss],{
							self.imgs: img_batch,
							self.labels: label_batch
							})
				print "[*] Iter {}, loss={}".format(int(self.global_step.eval()), loss)
				if self.global_step.eval()%self.test_per_iter == 0 or self.global_step.eval()==1:
					self.evaluate(split='train')
					self.evaluate(split='test')
	
	def evaluate(self, imgs=None, labels=None, split='test'):
	
		if split == 'test':
			imgs, labels = self.dataset.random_sample(-1, phase='test')
		elif split == 'train':
			imgs, labels = self.dataset.random_sample(10000, phase='train')

		num_test = imgs.shape[0]
		correct = 0.
		test_imgs = 0.
		avg_loss = 0.
		for idx in range(int(math.floor(num_test/self.batch_size))):
			img_batch = imgs[idx*self.batch_size:(idx+1)*self.batch_size]
			label_batch = labels[idx*self.batch_size:(idx+1)*self.batch_size]
			pred, loss = self.sess.run([self.out_argmax, self.loss],{
						self.imgs: img_batch,
						self.labels: label_batch
						})
			correct_batch = self.calc_top1(pred, label_batch)
			correct += correct_batch
			test_imgs += img_batch.shape[0]
			avg_loss += loss

		print '[+] Top1 {} accuracy = {}, loss = {}'.format(split, correct/test_imgs, avg_loss/math.floor(num_test/self.batch_size))
		self.save_model()

	def calc_top1(self, pred, label):
		correct = np.sum((pred==label)+0.)
		return correct

	def save_model(self, name='checkpoint'):
		if not os.path.exists(self.ckpt_dir):
			os.makedirs(self.ckpt_dir)
		self.saver.save(self.sess, os.path.join(self.ckpt_dir, name), global_step=int(self.global_step.eval()))


