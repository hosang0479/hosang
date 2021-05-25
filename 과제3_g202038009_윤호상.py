# -*- coding: utf-8 -*-
"""과제3_G202038009_윤호상.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1QYWq-1o6DU9_aoyV0EXWvGguGJhgFePd
"""

from google.colab import drive
drive.mount('./drive')

cd "/content/drive/MyDrive/DLFromScratch2-master"

# 해리포터 데이터를 이용한 문장생성
potter1_split = harry_potter1.split() # 파일을 읽은 후 공백으로 분리하여 배열화 시켰음

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F

import numpy as np
import pandas as pd
import os
from argparse import Namespace

from collections import Counter

config = Namespace(
    train_file='/content/drive/MyDrive/DLFromScratch2-master/potter1.txt', seq_size=7, batch_size=100
)

with open(config.train_file, 'r', encoding='utf-8') as f:
    text = f.read()
text = text.split() # 해리포터 파일을 읽은 후 공백으로 분리하여 배열으로 담음

# 중복 단어를 제거하고 word2index, index2word 형태의 데이터셋을 생성
# 이렇게 만들어진 데이텃셋을 통해서 각 문장을 어절 단위로 분리,
# 각 배열의 인덱스 값을 맵핑해서 문장을 숫자 형태의 값을 가진 데이터로 변경 
# 이 과정은 자연어를 이해하지 못하는 컴퓨터가 어떠한 작업을 수행할 수 있도록 수치 형태의 데이터로 변경하는 과정
word_counts = Counter(text)
sorted_vocab = sorted(word_counts, key=word_counts.get, reverse=True)
int_to_vocab = {k: w for k, w in enumerate(sorted_vocab)}
vocab_to_int = {w: k for k, w in int_to_vocab.items()}
n_vocab = len(int_to_vocab)

print('Vocabulary size', n_vocab)

int_text = [vocab_to_int[w] for w in text] # 전체 텍스트를 index로 변경

# 다음은 학습을 위한 데이터를 만드는 과정
# source_word와 target_word로 분리
# source_word 문장 배열 다음에 target_word가 순서대로 등장한다는 것을 모델이 학습
source_words = []
target_words = []
for i in range(len(int_text)):
    ss_idx, se_idx, ts_idx, te_idx = i, (config.seq_size+i), i+1, (config.seq_size+i)+1
    if len(int_text[ts_idx:te_idx]) >= config.seq_size:
        source_words.append(int_text[ss_idx:se_idx])
        target_words.append(int_text[ts_idx:te_idx])

# 여기서 문장의 크기는 7
#  더 큰 사이즈로 학습을 진행 시 계산량이 많아져서 학습 시간이 많이 필요

for s,t in zip(source_words[0:10], target_words[0:10]):
  print('source {} -> target {}'.format(s,t))

# 모델은 Encoder와 Decoder로 구성
# 이 두 모델을 사용하는 것이 Sequence2Sequece의 전형적인 구조입니다

## 아래는 Encoder의 구조임
# 두개의 값이 GRU 셀(Cell)로 들어가게됨
# 하나는 입력 값이 임베딩 레이어를 통해서 나오는 값과 또 하나는 이전 단계의 hidden 값 
# 최종 출력은 입력을 통해서 예측된 값인 output, 다음 단계에 입력으로 들어가는 hidden
# 기본 구조의 seq2seq 모델에서는 output 값은 사용하지 않고 이전 단계의 hidden 값을 사용
# 최종 hidden 값은 입력된 문장의 전체 정보를 어떤 고정된 크기의 Context Vector에 축약하고 있기 때문에 이 값을 Decoder의 입력으로 사용
# 이후에 테스트할 Attention 모델은 이러한 구조와는 달리 encoder의 출력 값을 사용하는 모델
# 이 값을 통해서 어디에 집중할지를 결정.

class Encoder(nn.Module):

    def __init__(self, input_size, hidden_size):
        super().__init__()
        self.hidden_size = hidden_size
        self.embedding = nn.Embedding(input_size, hidden_size) #199->10
        self.gru = nn.GRU(hidden_size, hidden_size) #20-20

    def forward(self, x, hidden):
        x = self.embedding(x).view(1,1,-1)
        #print('Encoder forward embedding size {}'.format(x.size()))
        x, hidden = self.gru(x, hidden)
        return x, hidden

# Decoder를 설계
# Decoder 역시 GRU 셀(Cell)을 가짐

class Decoder(nn.Module):
    def __init__(self, hidden_size, output_size):
        super().__init__()
        self.hidden_size = hidden_size
        self.embedding = nn.Embedding(output_size, hidden_size) #199->10
        self.gru = nn.GRU(hidden_size, hidden_size) #10->10
        self.out = nn.Linear(hidden_size, output_size) #10->199
        self.softmax = nn.LogSoftmax(dim=1)
        
    def forward(self, x, hidden):
        x = self.embedding(x).view(1,1,-1)
        x, hidden = self.gru(x, hidden)
        x = self.softmax(self.out(x[0]))
        return x, hidden

# GPU를 사용

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(device)

# 인코더와 디코더 입출력 정보를 셋팅

enc_hidden_size = 50
dec_hidden_size = enc_hidden_size
encoder = Encoder(n_vocab, enc_hidden_size).to(device) # source(199) -> embedding(10)
decoder = Decoder(dec_hidden_size, n_vocab).to(device) # embedding(199) -> target(199)

encoder_optimizer = optim.SGD(encoder.parameters(), lr=0.01)
decoder_optimizer = optim.SGD(decoder.parameters(), lr=0.01)

criterion = nn.NLLLoss()

# 데이터를 나눠서 훈련 할 수 있도록 배치 모델을 작성

pairs = list(zip(source_words, target_words))
def get_batch(pairs, batch_size):
  pairs_length = len(pairs)
  for ndx in range(0, pairs_length, batch_size):
    #print(ndx, min(ndx+batch_size, pairs_length))
    yield pairs[ndx:min(ndx+batch_size, pairs_length)]

# 해당 모델은 1번 학습을 수행. (1번 돌아가는데 40분 이상이 소요됨) 
# 각 batch, epoch 마다 loss 정보를 표시

number_of_epochs = 1
for epoch in range(number_of_epochs):
    total_loss = 0
    #for pair in get_batch(pairs, config.batch_size): # batch_size 30
    for pair in get_batch(pairs, 30): # batch_size 30
      batch_loss = 0
       
      for si, ti in pair:
        x = torch.Tensor(np.array([si])).long().view(-1,1).to(device)
        y = torch.Tensor(np.array([ti])).long().view(-1,1).to(device)
        encoder_hidden = torch.zeros(1,1,enc_hidden_size).to(device)

        for j in range(config.seq_size):
            _, encoder_hidden = encoder(x[j], encoder_hidden)

        decoder_hidden = encoder_hidden
        decoder_input = torch.Tensor([[0]]).long().to(device)

        loss = 0

        for k in range(config.seq_size):
            decoder_output, decoder_hidden = decoder(decoder_input, decoder_hidden)
            decoder_input = y[k]
            loss += criterion(decoder_output, y[k])

        batch_loss += loss.item()/config.seq_size
        encoder_optimizer.zero_grad()
        decoder_optimizer.zero_grad()

        loss.backward()

        encoder_optimizer.step()
        decoder_optimizer.step()

      total_loss += batch_loss/config.batch_size
      print('batch_loss {:.5f}'.format(batch_loss/config.batch_size))
    print('epoch {}, loss {:.10f}'.format(epoch, total_loss/(len(pairs)//config.batch_size)))

# 학습이 종료된 모델을 저장소에 저장
# 저장 할 때에 학습 정보가 저장되어 있는 config 내용도 포함

# Save best model weights.
torch.save({
  'encoder': encoder.state_dict(), 'decoder':decoder.state_dict(),
  'config': config,
}, '/content/drive/MyDrive/DLFromScratch2-master/model.genesis.210122')

# 학습이 완료된 후에 해당 모델이 잘 학습되었는지 확인
# night와 was를 이용한 문장이 무엇이 생성이 되는지를 확인함

decoded_words = []

words = [vocab_to_int['Harry'], vocab_to_int['was']]
x = torch.Tensor(words).long().view(-1,1).to(device)

encoder_hidden = torch.zeros(1,1,enc_hidden_size).to(device)

for j in range(x.size(0)):
    _, encoder_hidden = encoder(x[j], encoder_hidden)

decoder_hidden = encoder_hidden
decoder_input = torch.Tensor([[words[1]]]).long().to(device)  

for di in range(20):
  decoder_output, decoder_hidden = decoder(decoder_input, decoder_hidden)
  _, top_index = decoder_output.data.topk(1)
  decoded_words.append(int_to_vocab[top_index.item()])

  decoder_input = top_index.squeeze().detach()

predict_words = decoded_words    
predict_sentence = ' '.join(predict_words)
print(predict_sentence)

# 에폭과 배치가 적절하지 않아 문장이 제대로 생성되지 않음을 알 수 있음

from google.colab import drive
drive.mount('./drive')



cd "/content/drive/MyDrive/DLFromScratch2-master"

import sys
sys.path.append('..')
from dataset import sequence

(x_train, t_train), (x_test, t_test) = \
    sequence.load_data('addition.txt', seed=1984)
char_to_id, id_to_char = sequence.get_vocab()

print(x_train.shape, t_train.shape)
print(x_test.shape, t_test.shape)
# (45000, 7) (45000, 5)
# (5000, 7) (5000, 5)

print(x_train[0])
print(t_train[0])
# [ 3  0  2  0  0 11  5]
# [ 6  0 11  7  5]

print(''.join([id_to_char[c] for c in x_train[0]]))
print(''.join([id_to_char[c] for c in t_train[0]]))
# 71+118
# _189

# chap07/seq2seq.py
# coding: utf-8
import sys
sys.path.append('..')
from common.time_layers import *
from common.base_model import BaseModel


class Encoder:
    def __init__(self, vocab_size, wordvec_size, hidden_size):
        V, D, H = vocab_size, wordvec_size, hidden_size
        rn = np.random.randn

        embed_W = (rn(V, D) / 100).astype('f')
        lstm_Wx = (rn(D, 4 * H) / np.sqrt(D)).astype('f')
        lstm_Wh = (rn(H, 4 * H) / np.sqrt(H)).astype('f')
        lstm_b = np.zeros(4 * H).astype('f')

        self.embed = TimeEmbedding(embed_W)
        self.lstm = TimeLSTM(lstm_Wx, lstm_Wh, lstm_b, stateful=False)

        self.params = self.embed.params + self.lstm.params  # 리스트
        self.grads = self.embed.grads + self.lstm.grads  # 리스트
        self.hs = None

    def forward(self, xs):
        xs = self.embed.forward(xs)
        hs = self.lstm.forward(xs)
        self.hs = hs
        return hs[:, -1, :]  # 마지막 hidden state

    def backward(self, dh):
        dhs = np.zeros_like(self.hs)
        dhs[:, -1, :] = dh

        dout = self.lstm.backward(dhs)
        dout = self.embed.backward(dout)
        return dout


class Decoder:
    def __init__(self, vocab_size, wordvec_size, hidden_size):
        V, D, H = vocab_size, wordvec_size, hidden_size
        rn = np.random.randn

        embed_W = (rn(V, D) / 100).astype('f')
        lstm_Wx = (rn(D, 4 * H) / np.sqrt(D)).astype('f')
        lstm_Wh = (rn(H, 4 * H) / np.sqrt(H)).astype('f')
        lstm_b = np.zeros(4 * H).astype('f')
        affine_W = (rn(H, V) / np.sqrt(H)).astype('f')
        affine_b = np.zeros(V).astype('f')

        self.embed = TimeEmbedding(embed_W)
        self.lstm = TimeLSTM(lstm_Wx, lstm_Wh, lstm_b, stateful=True)
        self.affine = TimeAffine(affine_W, affine_b)

        self.params, self.grads = [], []
        for layer in (self.embed, self.lstm, self.affine):
            self.params += layer.params
            self.grads += layer.grads

    def forward(self, xs, h):
        self.lstm.set_state(h)

        out = self.embed.forward(xs)
        out = self.lstm.forward(out)
        score = self.affine.forward(out)
        return score

    def backward(self, dscore):
        dout = self.affine.backward(dscore)
        dout = self.lstm.backward(dout)
        dout = self.embed.backward(dout)
        dh = self.lstm.dh
        return dh

    def generate(self, h, start_id, sample_size):
        sampled = []
        sample_id = start_id
        self.lstm.set_state(h)

        for _ in range(sample_size):
            x = np.array(sample_id).reshape((1, 1))
            out = self.embed.forward(x)
            out = self.lstm.forward(out)
            score = self.affine.forward(out)

            sample_id = np.argmax(score.flatten())
            sampled.append(int(sample_id))

        return sampled


class Seq2seq(BaseModel):
    def __init__(self, vocab_size, wordvec_size, hidden_size):
        V, D, H = vocab_size, wordvec_size, hidden_size
        self.encoder = Encoder(V, D, H)
        self.decoder = Decoder(V, D, H)
        self.softmax = TimeSoftmaxWithLoss()

        self.params = self.encoder.params + self.decoder.params
        self.grads = self.encoder.grads + self.decoder.grads

    def forward(self, xs, ts):
        decoder_xs, decoder_ts = ts[:, :-1], ts[:, 1:]

        h = self.encoder.forward(xs)
        score = self.decoder.forward(decoder_xs, h)
        loss = self.softmax.forward(score, decoder_ts)
        return loss

    def backward(self, dout=1):
        dout = self.softmax.backward(dout)
        dh = self.decoder.backward(dout)
        dout = self.encoder.backward(dh)
        return dout

    def generate(self, xs, start_id, sample_size):
        h = self.encoder.forward(xs)
        sampled = self.decoder.generate(h, start_id, sample_size)
        return sampled

# coding: utf-8
import sys
sys.path.append('..')
from dataset import sequence


(x_train, t_train), (x_test, t_test) = \
    sequence.load_data('addition.txt', seed=1984)
char_to_id, id_to_char = sequence.get_vocab()

print(x_train.shape, t_train.shape)
print(x_test.shape, t_test.shape)
# (45000, 7) (45000, 5)
# (5000, 7) (5000, 5)

print(x_train[0])
print(t_train[0])
# [ 3  0  2  0  0 11  5]
# [ 6  0 11  7  5]

print(''.join([id_to_char[c] for c in x_train[0]]))
print(''.join([id_to_char[c] for c in t_train[0]]))
# 71+118
# _189

# coding: utf-8
import sys
sys.path.append('..')
from dataset import sequence


(x_train, t_train), (x_test, t_test) = \
    sequence.load_data('addition.txt', seed=1984)
char_to_id, id_to_char = sequence.get_vocab()

print(x_train.shape, t_train.shape)
print(x_test.shape, t_test.shape)
# (45000, 7) (45000, 5)
# (5000, 7) (5000, 5)

print(x_train[0])
print(t_train[0])
# [ 3  0  2  0  0 11  5]
# [ 6  0 11  7  5]

print(''.join([id_to_char[c] for c in x_train[0]]))
print(''.join([id_to_char[c] for c in t_train[0]]))
# 71+118
# _189

def eval_seq2seq(model, question, correct, id_to_char,
                 verbos=False, is_reverse=False):
    correct = correct.flatten()
    # 머릿글자
    start_id = correct[0]
    correct = correct[1:]
    guess = model.generate(question, start_id, len(correct))

    # 문자열로 변환
    question = ''.join([id_to_char[int(c)] for c in question.flatten()])
    correct = ''.join([id_to_char[int(c)] for c in correct])
    guess = ''.join([id_to_char[int(c)] for c in guess])

    if verbos:
        if is_reverse:
            question = question[::-1]

        colors = {'ok': '\033[92m', 'fail': '\033[91m', 'close': '\033[0m'}
        print('Q', question)
        print('T', correct)

        is_windows = os.name == 'nt'

        if correct == guess:
            mark = colors['ok'] + '☑' + colors['close']
            if is_windows:
                mark = 'O'
            print(mark + ' ' + guess)
        else:
            mark = colors['fail'] + '☒' + colors['close']
            if is_windows:
                mark = 'X'
            print(mark + ' ' + guess)
        print('---')

    return 1 if guess == correct else 0

def eval_seq2seq(model, question, correct, id_to_char,
                 verbos=False, is_reverse=False):
    correct = correct.flatten()
    # 머릿글자
    start_id = correct[0]
    correct = correct[1:]
    guess = model.generate(question, start_id, len(correct))

    # 문자열로 변환
    question = ''.join([id_to_char[int(c)] for c in question.flatten()])
    correct = ''.join([id_to_char[int(c)] for c in correct])
    guess = ''.join([id_to_char[int(c)] for c in guess])

    if verbos:
        if is_reverse:
            question = question[::-1]

        colors = {'ok': '\033[92m', 'fail': '\033[91m', 'close': '\033[0m'}
        print('Q', question)
        print('T', correct)

        is_windows = os.name == 'nt'

        if correct == guess:
            mark = colors['ok'] + '☑' + colors['close']
            if is_windows:
                mark = 'O'
            print(mark + ' ' + guess)
        else:
            mark = colors['fail'] + '☒' + colors['close']
            if is_windows:
                mark = 'X'
            print(mark + ' ' + guess)
        print('---')

    return 1 if guess == correct else 0

# coding: utf-8
import sys
sys.path.append('..')
import os
import numpy


id_to_char = {}
char_to_id = {}


def _update_vocab(txt):
    chars = list(txt)

    for i, char in enumerate(chars):
        if char not in char_to_id:
            tmp_id = len(char_to_id)
            char_to_id[char] = tmp_id
            id_to_char[tmp_id] = char


def load_data(file_name='addition.txt', seed=1984):
    file_path = os.path.dirname(os.path.abspath(__file__)) + '/' + file_name

    if not os.path.exists(file_path):
        print('No file: %s' % file_name)
        return None

    questions, answers = [], []

    for line in open(file_path, 'r'):
        idx = line.find('_')
        questions.append(line[:idx])
        answers.append(line[idx:-1])

    # 어휘 사전 생성
    for i in range(len(questions)):
        q, a = questions[i], answers[i]
        _update_vocab(q)
        _update_vocab(a)

    # 넘파이 배열 생성
    x = numpy.zeros((len(questions), len(questions[0])), dtype=numpy.int)
    t = numpy.zeros((len(questions), len(answers[0])), dtype=numpy.int)

    for i, sentence in enumerate(questions):
        x[i] = [char_to_id[c] for c in list(sentence)]
    for i, sentence in enumerate(answers):
        t[i] = [char_to_id[c] for c in list(sentence)]

    # 뒤섞기
    indices = numpy.arange(len(x))
    if seed is not None:
        numpy.random.seed(seed)
    numpy.random.shuffle(indices)
    x = x[indices]
    t = t[indices]

    # 검증 데이터셋으로 10% 할당
    split_at = len(x) - len(x) // 10
    (x_train, x_test) = x[:split_at], x[split_at:]
    (t_train, t_test) = t[:split_at], t[split_at:]

    return (x_train, t_train), (x_test, t_test)


def get_vocab():
    return char_to_id, id_to_char

# seq2seq 학습 코드
import sys
sys.path.append('..')
import numpy as np
import matplotlib.pyplot as plt
from dataset import sequence
from common.optimizer import Adam
from common.trainer import Trainer
from common.util import eval_seq2seq


# 데이터셋 읽기
(x_train, t_train), (x_test, t_test) = sequence.load_data('addition.txt')
char_to_id, id_to_char = sequence.get_vocab()

# 하이퍼파라미터 설정
vocab_size = len(char_to_id)
wordvec_size = 16
hideen_size = 128
batch_size = 128
max_epoch = 25
max_grad = 5.0

model = Seq2seq(vocab_size, wordvec_size, hideen_size)
optimizer = Adam()
trainer = Trainer(model, optimizer)

acc_list = []
for epoch in range(max_epoch):
    trainer.fit(x_train, t_train, max_epoch=1,
                batch_size=batch_size, max_grad=max_grad)

    correct_num = 0
    for i in range(len(x_test)):
        question, correct = x_test[[i]], t_test[[i]]
        verbose = i < 10
        correct_num += eval_seq2seq(model, question, correct,
                                    id_to_char, verbose)

    acc = float(correct_num) / len(x_test)
    acc_list.append(acc)
    print('검증 정확도 %.3f%%' % (acc * 100))