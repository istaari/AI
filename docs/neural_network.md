# Neural Network Learning Roadmap

> A structured path from perceptron fundamentals to LLM systems.

---

## Table of Contents

- [1. Neural Network Fundamentals](#1-neural-network-fundamentals)
  - [What is a Neural Network?](#what-is-a-neural-network)
  - [Perceptron](#perceptron)
  - [Multi-Layer Perceptron (MLP)](#multi-layer-perceptron-mlp)
  - [Forward Propagation](#forward-propagation)
  - [Backpropagation](#backpropagation)
  - [Chain Rule](#chain-rule)
  - [Gradient Descent](#gradient-descent)
  - [Loss Functions](#loss-functions)
    - [MSE](#mse)
    - [Cross-Entropy](#cross-entropy)
  - [Weight Initialization](#weight-initialization)
    - [Xavier / Glorot Initialization](#xavier--glorot-initialization)
    - [He Initialization](#he-initialization)
  - [Bias](#bias)
  - [Universal Approximation Theorem](#universal-approximation-theorem)

- [2. Activation Functions & Optimization](#2-activation-functions--optimization)
  - [Activation Functions](#activation-functions)
    - [Sigmoid](#sigmoid)
    - [Tanh](#tanh)
    - [ReLU](#relu)
    - [Leaky ReLU](#leaky-relu)
    - [GELU](#gelu)
    - [Softmax](#softmax)
  - [Optimization](#optimization)
    - [Batch, Mini-Batch & SGD](#batch-mini-batch--sgd)
    - [Momentum](#momentum)
    - [AdaGrad](#adagrad)
    - [RMSProp](#rmsprop)
    - [Adam](#adam)
    - [AdamW](#adamw)
    - [Learning Rate Scheduling](#learning-rate-scheduling)

- [3. Training Challenges & Regularization](#3-training-challenges--regularization)
  - [Challenges](#challenges)
    - [Vanishing Gradient](#vanishing-gradient)
    - [Exploding Gradient](#exploding-gradient)
    - [Dead ReLU](#dead-relu)
    - [Overfitting](#overfitting)
    - [Underfitting](#underfitting)
    - [Bias-Variance Tradeoff](#bias-variance-tradeoff)
  - [Regularization](#regularization)
    - [L1 vs L2 (Weight Decay)](#l1-vs-l2-weight-decay)
    - [Dropout](#dropout)
    - [Early Stopping](#early-stopping)
    - [Data Augmentation](#data-augmentation)
    - [Label Smoothing](#label-smoothing)
  - [Normalization](#normalization)
    - [BatchNorm](#batchnorm)
    - [LayerNorm](#layernorm)
    - [Residual Connections](#residual-connections)

- [4. Convolutional Neural Networks (CNNs)](#4-convolutional-neural-networks-cnns)
  - [Concepts](#cnn-concepts)
    - [Convolution](#convolution)
    - [Kernel / Filter](#kernel--filter)
    - [Padding](#padding)
    - [Stride](#stride)
    - [Pooling](#pooling)
    - [Receptive Field](#receptive-field)
    - [Depthwise Separable Convolution](#depthwise-separable-convolution)
    - [Dilated Convolution](#dilated-convolution)
  - [Architectures](#cnn-architectures)
    - [ResNet](#resnet)
    - [EfficientNet](#efficientnet)

- [5. Sequence Models](#5-sequence-models)
  - [RNN](#rnn)
  - [Bidirectional RNN](#bidirectional-rnn)
  - [LSTM](#lstm)
  - [GRU](#gru)
  - [Seq2Seq](#seq2seq)

- [6. Attention & Transformers](#6-attention--transformers)
  - [Attention](#attention)
    - [Query, Key, Value](#query-key-value)
    - [Scaled Dot-Product Attention](#scaled-dot-product-attention)
    - [Self-Attention](#self-attention)
    - [Multi-Head Attention](#multi-head-attention)
    - [Cross-Attention](#cross-attention)
  - [Transformer Architecture](#transformer-architecture)
    - [Encoder](#encoder)
    - [Decoder](#decoder)
    - [Positional Encoding](#positional-encoding)
    - [Feed Forward Network](#feed-forward-network)
    - [Masked Attention](#masked-attention)
  - [Variants](#transformer-variants)
    - [Encoder-only](#encoder-only)
    - [Encoder-Decoder](#encoder-decoder)
    - [Decoder-only](#decoder-only)

- [7. Embeddings & Evaluation](#7-embeddings--evaluation)
  - [Embeddings](#embeddings)
    - [One-Hot Encoding](#one-hot-encoding)
    - [Word2Vec](#word2vec)
    - [GloVe](#glove)
    - [Learned Embeddings](#learned-embeddings)
  - [Evaluation Metrics](#evaluation-metrics)
    - [Accuracy](#accuracy)
    - [Precision](#precision)
    - [Recall](#recall)
    - [F1-score](#f1-score)
    - [ROC-AUC](#roc-auc)
    - [Perplexity](#perplexity)

- [8. Practical Deep Learning](#8-practical-deep-learning)
  - [Transfer Learning](#transfer-learning)
  - [Fine-Tuning](#fine-tuning)
  - [Hyperparameter Tuning](#hyperparameter-tuning)

- [9. Large Language Models (LLMs)](#9-large-language-models-llms)
  - [LLM Fundamentals](#llm-fundamentals)
    - [What is a Language Model?](#what-is-a-language-model)
    - [What is an LLM?](#what-is-an-llm)
    - [Next-Token Prediction](#next-token-prediction)
    - [Autoregressive Generation](#autoregressive-generation)
    - [Tokenization](#tokenization)
    - [Context Window](#context-window)
    - [Decoding Strategies](#decoding-strategies)
  - [Training](#llm-training)
    - [Pretraining](#pretraining)
    - [Supervised Fine-Tuning (SFT)](#supervised-fine-tuning-sft)
    - [Instruction Tuning](#instruction-tuning)
    - [In-Context Learning](#in-context-learning)
    - [RLHF](#rlhf)
    - [DPO](#dpo)
  - [Efficient Fine-Tuning](#efficient-fine-tuning)
    - [LoRA](#lora)
    - [QLoRA](#qlora)
    - [PEFT](#peft)
  - [LLM Systems](#llm-systems)
    - [Scaling Laws](#scaling-laws)
    - [Mixture of Experts (MoE)](#mixture-of-experts-moe)
    - [KV Cache](#kv-cache)

- [10. High-Frequency Interview Comparisons](#10-high-frequency-interview-comparisons)
  - [Sequence Models](#sequence-model-comparisons)
    - [CNN vs RNN](#cnn-vs-rnn)
    - [RNN vs LSTM](#rnn-vs-lstm)
    - [LSTM vs GRU](#lstm-vs-gru)
    - [RNN vs Transformer](#rnn-vs-transformer)
  - [Transformers & LLMs](#transformer-llm-comparisons)
    - [Attention vs Self-Attention](#attention-vs-self-attention)
    - [Encoder-only vs Encoder-Decoder vs Decoder-only](#encoder-only-vs-encoder-decoder-vs-decoder-only)
    - [LM vs LLM](#lm-vs-llm)
    - [Pretraining vs Fine-Tuning](#pretraining-vs-fine-tuning)
    - [Instruction Tuning vs In-Context Learning](#instruction-tuning-vs-in-context-learning)
    - [LoRA vs Full Fine-Tuning](#lora-vs-full-fine-tuning)

---

## 1. Neural Network Fundamentals

### What is a Neural Network?

### Perceptron

### Multi-Layer Perceptron (MLP)

### Forward Propagation

### Backpropagation

### Chain Rule

### Gradient Descent

### Loss Functions

#### MSE

#### Cross-Entropy

### Weight Initialization

#### Xavier / Glorot Initialization

#### He Initialization

### Bias

### Universal Approximation Theorem

---

## 2. Activation Functions & Optimization

### Activation Functions

#### Sigmoid

#### Tanh

#### ReLU

#### Leaky ReLU

#### GELU

#### Softmax

### Optimization

#### Batch, Mini-Batch & SGD

#### Momentum

#### AdaGrad

#### RMSProp

#### Adam

#### AdamW

#### Learning Rate Scheduling

---

## 3. Training Challenges & Regularization

### Challenges

#### Vanishing Gradient

#### Exploding Gradient

#### Dead ReLU

#### Overfitting

#### Underfitting

#### Bias-Variance Tradeoff

### Regularization

#### L1 vs L2 (Weight Decay)

#### Dropout

#### Early Stopping

#### Data Augmentation

#### Label Smoothing

### Normalization

#### BatchNorm

#### LayerNorm

#### Residual Connections

---

## 4. Convolutional Neural Networks (CNNs)

### CNN Concepts

#### Convolution

#### Kernel / Filter

#### Padding

#### Stride

#### Pooling

#### Receptive Field

#### Depthwise Separable Convolution

#### Dilated Convolution

### CNN Architectures

#### ResNet

#### EfficientNet

---

## 5. Sequence Models

### RNN

### Bidirectional RNN

### LSTM

### GRU

### Seq2Seq

---

## 6. Attention & Transformers

### Attention

#### Query, Key, Value

#### Scaled Dot-Product Attention

#### Self-Attention

#### Multi-Head Attention

#### Cross-Attention

### Transformer Architecture

#### Encoder

#### Decoder

#### Positional Encoding

#### Feed Forward Network

#### Masked Attention

### Transformer Variants

#### Encoder-only

#### Encoder-Decoder

#### Decoder-only

---

## 7. Embeddings & Evaluation

### Embeddings

#### One-Hot Encoding

#### Word2Vec

#### GloVe

#### Learned Embeddings

### Evaluation Metrics

#### Accuracy

#### Precision

#### Recall

#### F1-score

#### ROC-AUC

#### Perplexity

---

## 8. Practical Deep Learning

### Transfer Learning

### Fine-Tuning

### Hyperparameter Tuning

---

## 9. Large Language Models (LLMs)

### LLM Fundamentals

#### What is a Language Model?

#### What is an LLM?

#### Next-Token Prediction

#### Autoregressive Generation

#### Tokenization

#### Context Window

#### Decoding Strategies

### LLM Training

#### Pretraining

#### Supervised Fine-Tuning (SFT)

#### Instruction Tuning

#### In-Context Learning

#### RLHF

#### DPO

### Efficient Fine-Tuning

#### LoRA

#### QLoRA

#### PEFT

### LLM Systems

#### Scaling Laws

#### Mixture of Experts (MoE)

#### KV Cache

---

## 10. High-Frequency Interview Comparisons

### Sequence Model Comparisons

#### CNN vs RNN

#### RNN vs LSTM

#### LSTM vs GRU

#### RNN vs Transformer

### Transformer & LLM Comparisons

#### Attention vs Self-Attention

#### Encoder-only vs Encoder-Decoder vs Decoder-only

#### LM vs LLM

#### Pretraining vs Fine-Tuning

#### Instruction Tuning vs In-Context Learning

#### LoRA vs Full Fine-Tuning

---

*Progress through sections 1 → 9 in order, then use section 10 as a revision checklist before interviews.*
