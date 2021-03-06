# -*- coding:utf-8 -*-

from six import iteritems

import json
import os
import multiprocessing
import numpy as np
import random
import codecs

class file_data_loader:
    def __next__(self):
        raise NotImplementedError
    
    def next(self):
        return self.__next__()

    def next_batch(self, batch_size):
        raise NotImplementedError

class npy_data_loader(file_data_loader):
    MODE_INSTANCE = 0      # One batch contains batch_size instances.
    MODE_ENTPAIR_BAG = 1   # One batch contains batch_size bags, instances in which have the same entity pair (usually for testing).
    MODE_RELFACT_BAG = 2   # One batch contains batch size bags, instances in which have the same relation fact. (usually for training).

    def __iter__(self):
        return self

    def __init__(self, data_dir, prefix, mode, word_vec_npy='vec.npy', shuffle=True, max_length=120, batch_size=160):
        if not os.path.isdir(data_dir):
            raise Exception("[ERROR] Data dir doesn't exist!")
        self.mode = mode
        self.shuffle = shuffle
        self.max_length = max_length
        self.batch_size = batch_size
        self.word_vec_mat = np.load(os.path.join(data_dir, word_vec_npy))
        self.data_word = np.load(os.path.join(data_dir, prefix + "_word.npy")) 
        self.data_pos1 = np.load(os.path.join(data_dir, prefix + "_pos1.npy")) 
        self.data_pos2 = np.load(os.path.join(data_dir, prefix + "_pos2.npy")) 
        self.data_mask = np.load(os.path.join(data_dir, prefix + "_mask.npy")) 
        self.data_rel = np.load(os.path.join(data_dir, prefix + "_label.npy")) 
        self.data_length = np.load(os.path.join(data_dir, prefix + "_len.npy")) 
        self.scope = np.load(os.path.join(data_dir, prefix + "_instance_scope.npy"))
        self.triple = np.load(os.path.join(data_dir, prefix + "_instance_triple.npy"))
        self.relfact_tot = len(self.triple)
        for i in range(self.scope.shape[0]):
            self.scope[i][1] += 1

        self.instance_tot = self.data_word.shape[0]
        self.rel_tot = 53

        if self.mode == self.MODE_INSTANCE:
            self.order = list(range(self.instance_tot))
        else:
            self.order = list(range(len(self.scope)))
        self.idx = 0

        if self.shuffle:
            random.shuffle(self.order) 

        print("Total relation fact: %d" % (self.relfact_tot))

    def __next__(self):
        return self.next_batch(self.batch_size)

    def next_batch(self, batch_size):
        if self.idx >= len(self.order):
            self.idx = 0
            if self.shuffle:
                random.shuffle(self.order) 
            raise StopIteration

        batch_data = {}

        if self.mode == self.MODE_INSTANCE:
            idx0 = self.idx
            idx1 = self.idx + batch_size
            if idx1 > len(self.order):
                self.idx = 0
                if self.shuffle:
                    random.shuffle(self.order) 
                raise StopIteration
            self.idx = idx1
            batch_data['word'] = self.data_word[idx0:idx1]
            batch_data['pos1'] = self.data_pos1[idx0:idx1]
            batch_data['pos2'] = self.data_pos2[idx0:idx1]
            batch_data['rel'] = self.data_rel[idx0:idx1]
            batch_data['length'] = self.data_length[idx0:idx1]
            batch_data['scope'] = np.stack([list(range(idx1 - idx0)), list(range(1, idx1 - idx0 + 1))], axis=1)
        elif self.mode == self.MODE_ENTPAIR_BAG or self.mode == self.MODE_RELFACT_BAG:
            idx0 = self.idx
            idx1 = self.idx + batch_size
            if idx1 > len(self.order):
                self.idx = 0
                if self.shuffle:
                    random.shuffle(self.order) 
                raise StopIteration
            self.idx = idx1
            _word = []
            _pos1 = []
            _pos2 = []
            _rel = []
            _ins_rel = []
            _multi_rel = []
            _length = []
            _scope = []
            _mask = []
            cur_pos = 0
            for i in range(idx0, idx1):
                _word.append(self.data_word[self.scope[self.order[i]][0]:self.scope[self.order[i]][1]])
                _pos1.append(self.data_pos1[self.scope[self.order[i]][0]:self.scope[self.order[i]][1]])
                _pos2.append(self.data_pos2[self.scope[self.order[i]][0]:self.scope[self.order[i]][1]])
                _rel.append(self.data_rel[self.scope[self.order[i]][0]])
                _ins_rel.append(self.data_rel[self.scope[self.order[i]][0]:self.scope[self.order[i]][1]])
                _length.append(self.data_length[self.scope[self.order[i]][0]:self.scope[self.order[i]][1]])
                _mask.append(self.data_mask[self.scope[self.order[i]][0]:self.scope[self.order[i]][1]])
                bag_size = self.scope[self.order[i]][1] - self.scope[self.order[i]][0]
                _scope.append([cur_pos, cur_pos + bag_size])
                cur_pos = cur_pos + bag_size
                if self.mode == self.MODE_ENTPAIR_BAG:
                    _one_multi_rel = np.zeros((self.rel_tot), dtype=np.int32)
                    for j in range(self.scope[self.order[i]][0], self.scope[self.order[i]][1]):
                        _one_multi_rel[self.data_rel[j]] = 1
                    _multi_rel.append(_one_multi_rel)
            batch_data['word'] = np.concatenate(_word)
            batch_data['pos1'] = np.concatenate(_pos1)
            batch_data['pos2'] = np.concatenate(_pos2)
            batch_data['rel'] = np.stack(_rel)
            batch_data['ins_rel'] = np.concatenate(_ins_rel)
            if self.mode == self.MODE_ENTPAIR_BAG:
                batch_data['multi_rel'] = np.stack(_multi_rel)
            batch_data['length'] = np.concatenate(_length)
            batch_data['scope'] = np.stack(_scope)
            batch_data['mask'] = np.concatenate(_mask)

        return batch_data

class json_file_data_loader(file_data_loader):
    MODE_INSTANCE = 0      # One batch contains batch_size instances.
    MODE_ENTPAIR_BAG = 1   # One batch contains batch_size bags, instances in which have the same entity pair (usually for testing).
    MODE_RELFACT_BAG = 2   # One batch contains batch size bags, instances in which have the same relation fact. (usually for training).

    def _load_preprocessed_file(self):
        name_prefix = '.'.join(self.file_name.split(os.sep)[-1].split('.')[:-1])
        word_vec_name_prefix = '.'.join(self.word_vec_file_name.split(os.sep)[-1].split('.')[:-1])
        processed_data_dir = '_processed_data'

        if not os.path.isdir(processed_data_dir):
            return False
        word_npy_file_name = os.path.join(processed_data_dir, name_prefix + '_word.npy')
        pos1_npy_file_name = os.path.join(processed_data_dir, name_prefix + '_pos1.npy')
        pos2_npy_file_name = os.path.join(processed_data_dir, name_prefix + '_pos2.npy')
        rel_npy_file_name = os.path.join(processed_data_dir, name_prefix + '_rel.npy')
        mask_npy_file_name = os.path.join(processed_data_dir, name_prefix + '_mask.npy')
        length_npy_file_name = os.path.join(processed_data_dir, name_prefix + '_length.npy')
        entpair2scope_file_name = os.path.join(processed_data_dir, name_prefix + '_entpair2scope.json')
        relfact2scope_file_name = os.path.join(processed_data_dir, name_prefix + '_relfact2scope.json')
        id2entity_file_name = os.path.join(processed_data_dir, name_prefix + '_id2entity.json')
        word_vec_mat_file_name = os.path.join(processed_data_dir, word_vec_name_prefix + '_mat.npy')
        word2id_file_name = os.path.join(processed_data_dir, word_vec_name_prefix + '_word2id.json')
        if not os.path.exists(word_npy_file_name) or \
           not os.path.exists(pos1_npy_file_name) or \
           not os.path.exists(pos2_npy_file_name) or \
           not os.path.exists(rel_npy_file_name) or \
           not os.path.exists(mask_npy_file_name) or \
           not os.path.exists(length_npy_file_name) or \
           not os.path.exists(entpair2scope_file_name) or \
           not os.path.exists(relfact2scope_file_name) or \
           not os.path.exists(id2entity_file_name) or \
           not os.path.exists(word_vec_mat_file_name) or \
           not os.path.exists(word2id_file_name):
            return False
        print("Pre-processed files exist. Loading them...")
        self.data_word = np.load(word_npy_file_name)
        self.data_pos1 = np.load(pos1_npy_file_name)
        self.data_pos2 = np.load(pos2_npy_file_name)
        self.data_rel = np.load(rel_npy_file_name)
        self.data_mask = np.load(mask_npy_file_name)
        self.data_length = np.load(length_npy_file_name)
        self.entpair2scope = json.load(codecs.open(entpair2scope_file_name, "r", "utf-8"))
        self.relfact2scope = json.load(codecs.open(relfact2scope_file_name, "r", "utf-8"))
        self.id2entity = json.load(codecs.open(id2entity_file_name, "r", "utf-8"))
        self.word_vec_mat = np.load(word_vec_mat_file_name)
        self.word2id = json.load(codecs.open(word2id_file_name, "r", "utf-8"))
        if self.data_word.shape[1] != self.max_length:
            print("Pre-processed files don't match current settings. Reprocessing...")
            return False
        print("Finish loading")
        return True

    def __init__(self, file_name, word_vec_file_name, rel2id_file_name, mode, shuffle=True, max_length=120, case_sensitive=False, reprocess=False, batch_size=160):
        '''
        file_name: Json file storing the data in the following format
            [
                {
                    'sentence': 'Bill Gates is the founder of Microsoft .',
                    'head': {'word': 'Bill Gates', ...(other information)},
                    'tail': {'word': 'Microsoft', ...(other information)},
                    'relation': 'founder'
                },
                ...
            ]
        word_vec_file_name: Json file storing word vectors in the following format
            [
                {'word': 'the', 'vec': [0.418, 0.24968, ...]},
                {'word': ',', 'vec': [0.013441, 0.23682, ...]},
                ...
            ]
        rel2id_file_name: Json file storing relation-to-id diction in the following format
            {
                'NA': 0
                'founder': 1
                ...
            }
            **IMPORTANT**: make sure the id of NA is 0!
        mode: Specify how to get a batch of data. See MODE_* constants for details.
        shuffle: Whether to shuffle the data, default as True. You should use shuffle when training.
        max_length: The length that all the sentences need to be extend to, default as 120. # 指的是每句话的长度
        case_sensitive: Whether the data processing is case-sensitive, default as False.
        reprocess: Do the pre-processing whether there exist pre-processed files, default as False.
        batch_size: The size of each batch, default as 160. # 指的是每批次多少句话
        '''

        self.file_name = file_name
        self.word_vec_file_name = word_vec_file_name
        self.case_sensitive = case_sensitive
        self.max_length = max_length
        self.mode = mode
        self.shuffle = shuffle
        self.batch_size = batch_size
        self.rel2id = json.load(codecs.open(rel2id_file_name, "r", "utf-8"))

        if reprocess or not self._load_preprocessed_file(): # Try to load pre-processed files:
        # if reprocess or self._load_preprocessed_file(): # Try to load pre-processed files:
            # Check files
            if file_name is None or not os.path.isfile(file_name):
                raise Exception("[ERROR] Data file doesn't exist")
            if word_vec_file_name is None or not os.path.isfile(word_vec_file_name):
                raise Exception("[ERROR] Word vector file doesn't exist")

            # Load files
            print("Loading data file...")
            self.ori_data = json.load(codecs.open(self.file_name, "r", "utf-8"))
            print("Finish loading")
            print("Loading word vector file...")
            self.ori_word_vec = json.load(
                codecs.open(self.word_vec_file_name, "r", "utf-8"))
            print("Finish loading")
            
            # Eliminate case sensitive
            if not case_sensitive:
                print("Elimiating case sensitive problem...")
                for i in range(len(self.ori_data)):
                    self.ori_data[i]['sentence'] = self.ori_data[i]['sentence'].lower()
                    self.ori_data[i]['head']['word'] = self.ori_data[i]['head']['word'].lower()
                    self.ori_data[i]['tail']['word'] = self.ori_data[i]['tail']['word'].lower()
                print("Finish eliminating")

            # Sort data by entities and relations
            print("Sort data...")

            self.ori_data.sort(key=lambda a: a['head']['id'] + '#' + a['tail']['id'] + '#' + a['relation'])
            print("Finish sorting")
       
            # Pre-process word vec
            self.word2id = {}
            self.word_vec_tot = len(self.ori_word_vec) # 词向量的总个数

            # 加入UNK和BLANK词
            UNK = self.word_vec_tot
            BLANK = self.word_vec_tot + 1
            
            self.word_vec_dim = len(self.ori_word_vec[0]['vec']) # 获取每个词的词向量的维度

            print("Got {} words of {} dims".format(self.word_vec_tot, self.word_vec_dim))
            print("Building word vector matrix and mapping...")
            self.word_vec_mat = np.zeros((self.word_vec_tot, self.word_vec_dim), dtype=np.float32) # 初始化词向量，为0，(word_vec_tot, word_vec_dim)


            for cur_id, word in enumerate(self.ori_word_vec):
                w = word['word']
                if not case_sensitive:
                    w = w.lower()
                self.word2id[w] = cur_id # 将词对应于index的id
                self.word_vec_mat[cur_id, :] = word['vec'] 

            # 将上文对应初始化的词向量更新为vec字典的向量, UNK和BLANK并没有为其赋值词向量

            self.word2id['UNK'] = UNK
            self.word2id['BLANK'] = BLANK
            print("Finish building") # 上面完成dict的构建
            

            # Pre-process data
            print("Pre-processing data...")
            self.instance_tot = len(self.ori_data) # 训练数据的长度
            self.entpair2scope = {} # (head, tail) -> scope
            self.relfact2scope = {} # (head, tail, relation) -> scope
            self.id2entity = {} # id和entity的一一对应
            self.data_word = np.zeros((self.instance_tot, self.max_length), dtype=np.int32)
            self.data_pos1 = np.zeros((self.instance_tot, self.max_length), dtype=np.int32) 
            self.data_pos2 = np.zeros((self.instance_tot, self.max_length), dtype=np.int32)
            self.data_rel = np.zeros((self.instance_tot), dtype=np.int32)
            self.data_mask = np.zeros((self.instance_tot, self.max_length), dtype=np.int32)
            self.data_length = np.zeros((self.instance_tot), dtype=np.int32)
            last_entpair = ''
            last_entpair_pos = -1
            last_relfact = ''
            last_relfact_pos = -1


            for i in range(self.instance_tot):
                ins = self.ori_data[i]
                if ins['relation'] in self.rel2id:
                    self.data_rel[i] = self.rel2id[ins['relation']]
                else:
                    self.data_rel[i] = self.rel2id['NA']
                
                sentence = ' '.join(ins['sentence'].split()) # delete extra spaces 删除多余的空格
                
                head = ins['head']['word']
                tail = ins['tail']['word']
                cur_entpair = ins['head']['id'] + '#' + ins['tail']['id'] # 拼接了头和尾的数据
                cur_relfact = ins['head']['id'] + '#' + ins['tail']['id'] + '#' + ins['relation'] # 拼接了头尾还有关系的数据

                

                if cur_entpair != last_entpair:
                    if last_entpair != '':
                        self.entpair2scope[last_entpair] = [last_entpair_pos, i] # left closed right open 得到同一cur_entpair的数据索引范围

                    last_entpair = cur_entpair
                    last_entpair_pos = i
                
                if cur_relfact != last_relfact:
                    if last_relfact != '':
                        self.relfact2scope[last_relfact] = [last_relfact_pos, i]
                    last_relfact = cur_relfact
                    last_relfact_pos = i
                
                pos1 = sentence.find(head)
                pos2 = sentence.find(tail)

                # p1为句子中head的位置索引，p2为句子中tail的位置索引
                pos1 += 1
                pos2 += 1
                

                cur_ref_data_word = self.data_word[i]         

                # pos1为head的开头词在句子中的索引位置，pos2为tail的起始词在句子中的索引位置
                for j in range(min(max_length, len(sentence))):
                    word = sentence[j]
                    if word in self.word2id:
                        cur_ref_data_word[j] = self.word2id[word]
                    else:
                        cur_ref_data_word[j] = UNK
                    

                # 对最大长度外的单词赋值为BLANK
                for j in range(j + 1, max_length):
                    cur_ref_data_word[j] = BLANK
                
                self.data_length[i] = len(sentence)  # 存储每个句子的长度，为mask做准备

                if len(sentence) > max_length:  # 对于长于max_length的单词进行舍弃
                    self.data_length[i] = max_length
                
                if pos1 == -1 or pos2 == -1:
                    raise Exception("[ERROR] Position error, index = {}, sentence = {}, head = {}, tail = {}".format(i, sentence, head, tail))
                if pos1 >= max_length:
                    pos1 = max_length - 1
                if pos2 >= max_length:
                    pos2 = max_length - 1
                
                
                pos_min = min(pos1, pos2)
                pos_max = max(pos1, pos2)
                for j in range(max_length):
                    self.data_pos1[i][j] = j - pos1 + max_length # data_pos里面的值为实际索引值距离最大长度的值，相当于revert数据，将空格翻转到前面
                    self.data_pos2[i][j] = j - pos2 + max_length
                    if j >= self.data_length[i]: # 定义mask，没有单词的为0，小于pos_min为1，pos_min到pos_max之间为2，大于pos_max的为3
                        self.data_mask[i][j] = 0
                    elif j <= pos_min:
                        self.data_mask[i][j] = 1
                    elif j <= pos_max:
                        self.data_mask[i][j] = 2
                    else:
                        self.data_mask[i][j] = 3


            if last_entpair != '': # 最后一个句子的entpair2scope数据
                self.entpair2scope[last_entpair] = [last_entpair_pos, self.instance_tot] # left closed right open
            if last_relfact != '':
                self.relfact2scope[last_relfact] = [last_relfact_pos, self.instance_tot]

            for item in self.ori_data:
                self.id2entity[item["head"]["id"]] = item["head"]["word"]
                self.id2entity[item["tail"]["id"]] = item["tail"]["word"]


            print("Finish pre-processing")     
            print("Storing processed files...")

            name_prefix = '.'.join(file_name.split(os.sep)[-1].split('.')[:-1])
            word_vec_name_prefix = '.'.join(word_vec_file_name.split(os.sep)[-1].split('.')[:-1])
            processed_data_dir = '_processed_data'
            if not os.path.isdir(processed_data_dir):
                os.mkdir(processed_data_dir)
            
            np.save(os.path.join(processed_data_dir, name_prefix + '_word.npy'), self.data_word)
            np.save(os.path.join(processed_data_dir, name_prefix + '_pos1.npy'), self.data_pos1)
            np.save(os.path.join(processed_data_dir, name_prefix + '_pos2.npy'), self.data_pos2)
            np.save(os.path.join(processed_data_dir, name_prefix + '_rel.npy'), self.data_rel)
            np.save(os.path.join(processed_data_dir, name_prefix + '_mask.npy'), self.data_mask)
            np.save(os.path.join(processed_data_dir, name_prefix + '_length.npy'), self.data_length)
            np.save(os.path.join(processed_data_dir, word_vec_name_prefix + '_mat.npy'), self.word_vec_mat)

            json.dump(self.entpair2scope, codecs.open(os.path.join(
                processed_data_dir, name_prefix + '_entpair2scope.json'), 'w',  "utf-8"), ensure_ascii=False, indent=2)
            json.dump(self.relfact2scope, codecs.open(os.path.join(
                processed_data_dir, name_prefix + '_relfact2scope.json'), 'w', "utf-8"), ensure_ascii=False, indent=2)
            json.dump(self.word2id, codecs.open(os.path.join(
                processed_data_dir, word_vec_name_prefix + '_word2id.json'), 'w', "utf-8"), ensure_ascii=False, indent=2)

            json.dump(self.id2entity, codecs.open(os.path.join(
                processed_data_dir, name_prefix + '_id2entity.json'), 'w', "utf-8"), ensure_ascii=False, indent=2)

            
            print("Finish storing") # 完成数据的存储

            # code.interact(local=locals())

        # Prepare for idx
        self.instance_tot = self.data_word.shape[0] # 实例的数量
        self.entpair_tot = len(self.entpair2scope) # 总共有多少对
        self.relfact_tot = 0 # The number of relation facts, without NA. 统计relfact对，除去NA的数据
        for key in self.relfact2scope:
            if key[-2:] != 'NA':
                self.relfact_tot += 1
        self.rel_tot = len(self.rel2id) # 总共的关系


        if self.mode == self.MODE_INSTANCE:
            self.order = list(range(self.instance_tot))
        elif self.mode == self.MODE_ENTPAIR_BAG: # 常用于测试 数据没有带上关系
            self.order = list(range(len(self.entpair2scope)))
            self.scope_name = []
            self.scope = []

            for key, value in iteritems(self.entpair2scope):
                self.scope_name.append(key)
                self.scope.append(value)
        elif self.mode == self.MODE_RELFACT_BAG: # 常用于训练 数据带上了关系
            self.order = list(range(len(self.relfact2scope)))
            self.scope_name = []
            self.scope = []
            for key, value in iteritems(self.relfact2scope):
                self.scope_name.append(key)
                self.scope.append(value)
        else:
            raise Exception("[ERROR] Invalid mode")
        self.idx = 0

        if self.shuffle: # 随机化数据
            random.shuffle(self.order) 

        print("Total relation fact: %d" % (self.relfact_tot))

    def __iter__(self):
        return self

    def __next__(self):
        return self.next_batch(self.batch_size)

    def next_batch(self, batch_size): # TODO read
        if self.idx >= len(self.order):
            self.idx = 0
            if self.shuffle:
                random.shuffle(self.order) 
            raise StopIteration

        batch_data = {}

        if self.mode == self.MODE_INSTANCE:
            idx0 = self.idx
            idx1 = self.idx + batch_size
            if idx1 > len(self.order):
                idx1 = len(self.order)
            self.idx = idx1
            batch_data['word'] = self.data_word[idx0:idx1]
            batch_data['pos1'] = self.data_pos1[idx0:idx1]
            batch_data['pos2'] = self.data_pos2[idx0:idx1]
            batch_data['rel'] = self.data_rel[idx0:idx1]
            batch_data['mask'] = self.data_mask[idx0:idx1]
            batch_data['length'] = self.data_length[idx0:idx1]
            batch_data['scope'] = np.stack([list(range(batch_size)), list(range(1, batch_size + 1))], axis=1)
            if idx1 - idx0 < batch_size:
                padding = batch_size - (idx1 - idx0)
                batch_data['word'] = np.concatenate([batch_data['word'], np.zeros((padding, self.data_word.shape[-1]), dtype=np.int32)])
                batch_data['pos1'] = np.concatenate([batch_data['pos1'], np.zeros((padding, self.data_pos1.shape[-1]), dtype=np.int32)])
                batch_data['pos2'] = np.concatenate([batch_data['pos2'], np.zeros((padding, self.data_pos2.shape[-1]), dtype=np.int32)])
                batch_data['mask'] = np.concatenate([batch_data['mask'], np.zeros((padding, self.data_mask.shape[-1]), dtype=np.int32)])
                batch_data['rel'] = np.concatenate([batch_data['rel'], np.zeros((padding), dtype=np.int32)])
                batch_data['length'] = np.concatenate([batch_data['length'], np.zeros((padding), dtype=np.int32)])
        elif self.mode == self.MODE_ENTPAIR_BAG or self.mode == self.MODE_RELFACT_BAG:
            idx0 = self.idx
            idx1 = self.idx + batch_size
            if idx1 > len(self.order):
                idx1 = len(self.order)
            self.idx = idx1
            _word = []
            _pos1 = []
            _pos2 = []
            _mask = []
            _rel = []
            _ins_rel = []
            _multi_rel = []
            _entpair = []
            _length = []
            _scope = []
            cur_pos = 0
            for i in range(idx0, idx1):
                _word.append(self.data_word[self.scope[self.order[i]][0]:self.scope[self.order[i]][1]])
                _pos1.append(self.data_pos1[self.scope[self.order[i]][0]:self.scope[self.order[i]][1]])
                _pos2.append(self.data_pos2[self.scope[self.order[i]][0]:self.scope[self.order[i]][1]])
                _mask.append(self.data_mask[self.scope[self.order[i]][0]:self.scope[self.order[i]][1]])
                _rel.append(self.data_rel[self.scope[self.order[i]][0]])
                _ins_rel.append(self.data_rel[self.scope[self.order[i]][0]:self.scope[self.order[i]][1]])
                _length.append(self.data_length[self.scope[self.order[i]][0]:self.scope[self.order[i]][1]])
                bag_size = self.scope[self.order[i]][1] - self.scope[self.order[i]][0]
                _scope.append([cur_pos, cur_pos + bag_size])
                cur_pos = cur_pos + bag_size
                if self.mode == self.MODE_ENTPAIR_BAG:
                    _one_multi_rel = np.zeros((self.rel_tot), dtype=np.int32)
                    for j in range(self.scope[self.order[i]][0], self.scope[self.order[i]][1]):
                        _one_multi_rel[self.data_rel[j]] = 1
                    _multi_rel.append(_one_multi_rel)
                    _entpair.append(self.scope_name[self.order[i]])
            for i in range(batch_size - (idx1 - idx0)):
                _word.append(np.zeros((1, self.data_word.shape[-1]), dtype=np.int32))
                _pos1.append(np.zeros((1, self.data_pos1.shape[-1]), dtype=np.int32))
                _pos2.append(np.zeros((1, self.data_pos2.shape[-1]), dtype=np.int32))
                _mask.append(np.zeros((1, self.data_mask.shape[-1]), dtype=np.int32))
                _rel.append(0)
                _ins_rel.append(np.zeros((1), dtype=np.int32))
                _length.append(np.zeros((1), dtype=np.int32))
                _scope.append([cur_pos, cur_pos + 1])
                cur_pos += 1
                if self.mode == self.MODE_ENTPAIR_BAG:
                    _multi_rel.append(np.zeros((self.rel_tot), dtype=np.int32))
                    _entpair.append('None#None')
            batch_data['word'] = np.concatenate(_word)
            batch_data['pos1'] = np.concatenate(_pos1)
            batch_data['pos2'] = np.concatenate(_pos2)
            batch_data['mask'] = np.concatenate(_mask)
            batch_data['rel'] = np.stack(_rel)
            batch_data['ins_rel'] = np.concatenate(_ins_rel)
            if self.mode == self.MODE_ENTPAIR_BAG:
                batch_data['multi_rel'] = np.stack(_multi_rel)
                batch_data['entpair'] = _entpair
            batch_data['length'] = np.concatenate(_length)
            batch_data['scope'] = np.stack(_scope)

        return batch_data
