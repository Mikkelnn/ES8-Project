import numpy as np

events = np.array([(0, 3), (5, 10), (4, 7), (9, 16)])
# 0123456789#
# |--|
#      |----|
#     |--|
#           |--|

start_times = [x[0] for x in events]
end_times = [x[1] for x in events]

ident = np.ones((events.shape[0], 1))

matrix_start = ident * start_times
matrix_end = ident * end_times

print("start overlap:\n", matrix_start - matrix_start.T)
print("start,end overlap:\n", matrix_end.T - matrix_start)

print("overlap:\n", matrix_start - matrix_start.T - matrix_end.T - matrix_start)
