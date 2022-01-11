import sys, logging
sys.path.append('../')
import random

class AllToOne_attack(object):
    '''
    any label -> fix_target
    '''
    @classmethod
    def add_argument(self, parser):
        parser.add_argument('--target_label (only one)', type=int,
                            help='target label')
        return parser
    def __init__(self, target_label):
        self.target_label = target_label
    def __call__(self, original_label, original_index = None, img = None):
        return self.poison_label(original_label)
    def poison_label(self, original_label):
        return self.target_label

class AllToAll_shiftLabelAttack(object):
    '''
    any label -> (label + fix_shift_amount)%num_classses
    '''
    @classmethod
    def add_argument(self, parser):
        parser.add_argument('--shift_amount', type=int,
                            help='shift_amount of all_to_all attack')
        parser.add_argument('--num_classses', type=int,
                            help='total number of labels')
        return parser
    def __init__(self, shift_amount, num_classses):
        self.shift_amount = shift_amount
        self.num_classses = num_classses
    def __call__(self, original_label, original_index = None, img = None):
        return self.poison_label(original_label)
    def poison_label(self, original_label):
        label_after_shift = (original_label + self.shift_amount)% self.num_classses
        return label_after_shift

class OneToAll_randomLabelAttack(object):
    '''
    Specific label -> random label among a set
    '''

    @classmethod
    def add_argument(self, parser):
        parser.add_argument('--source_label', type=int,
                            help='source_label(only one)')
        parser.add_argument('--random_target_label_list', type=list,
                            help='given list of target labels in one to all random label attack')
        return parser

    def __init__(self, specific_label, random_label_list):
        self.specific_label = specific_label
        self.random_label_list = random_label_list

    def __call__(self, original_label, original_index = None, img = None):
        return self.poison_label(original_label)

    def poison_label(self, original_label):
        if original_label == self.specific_label:
            return random.choice(self.random_label_list)
        else:
            return original_label

class OneToOne_attack(object):

    @classmethod
    def add_argument(self, parser):
        parser.add_argument('--source_label', type=int,
                            help='source_label(only one)')
        parser.add_argument('--target_label', type=int,
                            help='target label (only one)')
        return parser

    def __init__(self, source_label, target_label):
        self.source_label = source_label
        self.target_label = target_label

    def __call__(self, original_label, original_index = None, img = None):
        return self.poison_label(original_label)

    def poison_label(self, original_label):
        if original_label == self.source_label:
            return self.target_label
        else:
            return original_label

if __name__ == '__main__':
    a = AllToOne_attack(target_label=4)
    b = AllToAll_shiftLabelAttack(2, 10)
    c = OneToAll_randomLabelAttack(3, [4,5,6])
    d = OneToOne_attack(3,4)
    print(a(10))
    print(b(9))
    print(c(2))
    print(c(3))
    print(c(3))
    print(c(3))
    print(d(1))
    print(d(3))