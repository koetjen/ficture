import sys, os, copy, gc, re, gzip, pickle, argparse, logging, warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.manifold import MDS
import sklearn.neighbors
from scipy.sparse import coo_array

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utilt import plot_colortable

parser = argparse.ArgumentParser()
parser.add_argument('--input', type=str, help='')
parser.add_argument('--output', type=str, help='')
parser.add_argument('--cmap_name', type=str, default="turbo", help="Name of Matplotlib colormap to use")
args = parser.parse_args()

df = pd.read_csv(args.input, sep='\t', header=0)
df.rename(columns = {"X":"x","Y":"y"},inplace=True)
header = df.columns
factor_header = []
for x in header:
    y = re.match('^[A-Za-z]*_*(\d+)$', x)
    if y:
        factor_header.append(y.group(0))
K = len(factor_header)
N = df.shape[0]

# Posterior weight of factors
weight = df.loc[:, factor_header].sum(axis = 0)
weight = np.log(weight)
weight /= weight.sum()

# Find neearest neighbors
bt = sklearn.neighbors.BallTree(df.loc[:, ["x", "y"]])
dist, indx = bt.query(df.loc[:, ["x", "y"]], k = 7, return_distance=True)
r_indx = np.array([i for i,v in enumerate(indx) for y in range(len(v))], dtype=int)
c_indx = indx.reshape(-1)
dist = dist.reshape(-1)
nn = dist[dist > 0].min()
mask = (dist < nn + .5) & (dist > 0)
r_indx = r_indx[mask]
c_indx = c_indx[mask]
# Compute spatial similarity
Sig = coo_array((np.ones(len(r_indx)), (r_indx, c_indx)), shape=(N, N)).tocsr()
W = np.array(df.loc[:, factor_header])
mtx = W.T @ Sig @ W
# Translate into a symmetric dissimilarity measure
# Large values in mtx indicate close proximity, to be mapped to distinct colors
np.fill_diagonal(mtx, 0)
mtx /= mtx.sum(axis = 1)
mtx = mtx + mtx.T
# zz - Previous approach
# mtx = 1. - np.array(df.loc[:, factor_header].corr())
linear = MDS(n_components=1, dissimilarity="precomputed").fit_transform(mtx).squeeze()
c_order = np.argsort(linear)

# Allocate color range to factors depending on factor weight
c_order = np.argsort(linear)
c_weight = weight[c_order]
c_up = np.cumsum(c_weight)
c_down = np.concatenate([[0], np.cumsum(c_weight[:-1]) ])
c_pos = (c_up + c_down)/2

# Colormap
cmap_name = args.cmap_name
if args.cmap_name not in plt.colormaps():
    cmap_name = "turbo"
cmtx = plt.get_cmap('turbo')(c_pos) # K x 4

# Output RGB table
df = pd.DataFrame({"Name":range(K), "Color_index":c_order,\
        "R":cmtx[c_order, 0], "G":cmtx[c_order, 1], "B":cmtx[c_order, 2]})
f = args.output + ".rgb.tsv"
df.to_csv(f, sep='\t', index=False)

# Plot color bar
cdict = {i:cmtx[x,:] for i,x in enumerate(c_order)}
fig = plot_colortable(cdict, "Factor label", sort_colors=False, ncols=4)
f = args.output + ".cbar"
fig.savefig(f, format="png", transparent=True)
