# mcts algorithm
import numpy as np 


class Node:
    def __init__(self, board, parent):
        self.board = board 
        
        self.parent = parent 
