import sys, os, gc, gzip
import argparse
import numpy as np
import pandas as pd
from scipy.sparse import *

# Add parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hexagon_fn import *

parser = argparse.ArgumentParser()
parser.add_argument('--input_path', type=str, help='')
parser.add_argument('--output_path', type=str, help='')
parser.add_argument("--meta_data", type=str, help="Per tile meta data menifest.tsv")
parser.add_argument("--layout", type=str, help="Layout file of tiles to draw [lane] [tile] [row] [col] format in each line")
parser.add_argument('--lane', type=str, help='')
parser.add_argument('--tile', type=str, help='',default='')

parser.add_argument('--mu_scale', type=float, default=26.67, help='Coordinate to um translate')
parser.add_argument('--key', default = 'gn', type=str, help='gt: genetotal, gn: gene, spl: velo-spliced, unspl: velo-unspliced, velo: velo total')
parser.add_argument('--precision', type=int, default=1, help='Number of digits to store spatial location (in um), 0 for integer.')
parser.add_argument('--hex_width', type=int, default=24, help='')
parser.add_argument('--hex_radius', type=int, default=-1, help='')
parser.add_argument('--n_move', type=int, default=1, help='')
parser.add_argument('--min_ct_per_unit', type=int, default=1, help='')
parser.add_argument('--min_count_per_feature', type=int, default=1, help='')

args = parser.parse_args()

path=args.input_path
lane=args.lane
mu_scale = 1./args.mu_scale

diam=args.hex_width
radius=args.hex_radius
if radius < 0:
    radius = diam / np.sqrt(3)
else:
    diam = int(radius*np.sqrt(3))

### Output
if not os.path.exists(args.output_path):
    arg="mkdir -p " + args.output_path
    os.system(arg)

### Menifest
mani=pd.read_csv(args.meta_data, sep='\t')
mani["lane"] = mani["id"].map(lambda x : x.split('_')[0]).astype(int)
mani["tile"] = mani["id"].map(lambda x : x.split('_')[1]).astype(int)
mani = mani[mani.lane.eq(int(lane))]

xbin_min, xbin_max = mani.xmin.min(), mani.xmax.max()
ybin_min, ybin_max = mani.ymin.min(), mani.ymax.max()
xr = xbin_max-xbin_min+1
yr = ybin_max-ybin_min+1
print(f"Read meta data. Xmax, Ymax: {xbin_max}, {ybin_max}")

### Layout
layout = pd.read_csv(args.layout, sep='\t', dtype=int)
layout = layout[layout.lane.eq(int(lane))]
layout.sort_values(by = ['lane', 'row', 'col'], inplace=True)
tile_list = layout.tile.astype(str).values
df = layout.merge(right = mani[["lane", "tile", 'xmin', 'xmax', 'ymin', 'ymax']], on = ["lane", "tile"], how = "left")
df.row = df.row - df.row.min()
df.col = df.col - df.col.min()
nrows = df.row.max() + 1
ncols = df.col.max() + 1
lanes = []
tiles = []
for i in range(nrows):
    lanes.append( [None] * ncols )
    tiles.append( [None] * ncols )
for index, row in df.iterrows():
    i = int(row['row'])
    j = int(row['col'])
    lanes[i][j] = str(row['lane'])
    tiles[i][j] = str(row['tile'])
# Code the output as the tile numbers of the lower-left and upper-right corners
tile_ll = tiles[-1][0]
tile_ur = tiles[0][-1]
print(f"Read layout info. lane {lane}, tile {tile_ll}-{tile_ur}")


f = path + "/barcodes.tsv.gz"
brc = pd.read_csv(gzip.open(f, 'rb'), sep='\t|,', names=["barcode","j","v2",\
    "lane","tile","X","Y","brc_tot_gn","brc_tot_gt",\
    "brc_tot_spl","brc_tot_unspl","brc_tot_ambig"],\
    usecols=["j","lane","tile","X","Y"], engine='python')
f = path + "/matrix.mtx.gz"
df = pd.read_csv(gzip.open(f, 'rb'), sep=' ', skiprows=3, names=["i","j",\
    "gn","gt","spl","unspl","ambig"],\
    usecols=["i","j",args.key])
df = df.merge(right = brc, on = 'j', how = 'inner')
f = path+"/features.tsv.gz"
feature = pd.read_csv(gzip.open(f, 'rb'), sep='\t|,', names=["gene_id","gene",\
    "i","gene_tot_gn","gene_tot_gt",\
    "gene_tot_spl","gene_tot_unspl","gene_tot_ambig"],\
    usecols=["i","gene","gene_id"],  engine='python')
df = df.merge(right = feature, on = 'i', how = 'inner')
df.drop(columns = ['i', 'j'], inplace=True)
df.lane = df.lane.astype(str)
df.tile = df.tile.astype(str)

for itr_r in range(len(lanes)):
    for itr_c in range(len(lanes[0])):
        lane, tile = lanes[itr_r][itr_c], tiles[itr_r][itr_c]
        indx = df.lane.eq(lane) & df.tile.eq(tile)
        df.loc[indx, 'X'] = (nrows - itr_r - 1) * xr + df.loc[indx, 'X'].values - xbin_min
        df.loc[indx, 'Y'] = itr_c * yr + df.loc[indx, 'Y'].values - ybin_min
        print(f"{lane}_{tile}")

df['j'] = df.lane.values + '_' + df.tile.values + '_' + df.X.astype(str) + '_' + df.Y.astype(str)

feature = df[['gene','gene_id',args.key]].groupby(by = ['gene', 'gene_id'], as_index=False).agg({args.key:sum}).rename(columns = {args.key:'gene_tot'})
feature = feature.loc[feature.gene_tot > args.min_count_per_feature, :]
gene_kept = list(feature['gene'])
df = df[df.gene.isin(gene_kept)]
df['j'] = df.X.astype(str) + '_' + df.Y.astype(str)

brc = df.groupby(by = ['j','tile','X','Y']).agg({args.key: sum}).reset_index()
brc.index = range(brc.shape[0])
pixel_ct = brc[args.key].values
pts = np.asarray(brc[['X','Y']]) * mu_scale
pts_tile = brc.tile.astype(int).values
print(f"Read data with {brc.shape[0]} pixels and {len(gene_kept)} genes.")
df.drop(columns = ['X', 'Y'], inplace=True)

# Make DGE
feature_kept = copy.copy(gene_kept)
barcode_kept = list(brc.j.values)
del brc
gc.collect()
bc_dict = {x:i for i,x in enumerate( barcode_kept ) }
ft_dict = {x:i for i,x in enumerate( feature_kept ) }
indx_row = [ bc_dict[x] for x in df['j']]
indx_col = [ ft_dict[x] for x in df['gene']]
N = len(barcode_kept)
M = len(feature_kept)
T = df[args.key].sum()
dge_mtx = coo_matrix((df[args.key].values, (indx_row, indx_col)), shape=(N, M)).tocsr()
feature_mf = np.asarray(dge_mtx.sum(axis = 0)).reshape(-1)
feature_mf = feature_mf / feature_mf.sum()
total_molecule=df[args.key].sum()
print(f"Made DGE {dge_mtx.shape}")
del df
gc.collect()

feature['dummy'] = "Gene Expression"
f = args.output_path + "/features.tsv.gz"
feature[['gene_id','gene','dummy']].to_csv(f, sep='\t', index=False, header=False)

brc_f = args.output_path + "/barcodes.tsv"
mtx_f = args.output_path + "/matrix.mtx"
# If exists, delete
if os.path.exists(brc_f):
    _ = os.system("rm " + brc_f)
if os.path.exists(mtx_f):
    _ = os.system("rm " + mtx_f)

n_move = args.n_move
if n_move > diam:
    n_move = diam // 4

b_size = 512
offs_x = 0
offs_y = 0
n_unit = 0
while offs_x < n_move:
    while offs_y < n_move:
        x,y = pixel_to_hex(pts, radius, offs_x/n_move, offs_y/n_move)
        hex_crd = list(zip(x,y))
        ct = pd.DataFrame({'hex_id':hex_crd, 'tot':pixel_ct}).groupby(by = 'hex_id').agg({'tot': sum}).reset_index()
        mid_ct = np.median(ct.loc[ct.tot >= args.min_ct_per_unit, 'tot'].values)
        ct = set(ct.loc[ct.tot >= args.min_ct_per_unit, 'hex_id'].values)
        hex_list = list(ct)
        hex_dict = {x:i for i,x in enumerate(hex_list)}
        sub = pd.DataFrame({'crd':hex_crd,'cCol':range(N), 'X':pts[:, 0], 'Y':pts[:, 1], 'tile':pts_tile})
        sub = sub[sub.crd.isin(ct)]
        sub['cRow'] = sub.crd.map(hex_dict).astype(int)

        brc = sub[['cRow', 'tile', 'X', 'Y']].groupby(by = 'cRow').agg({'X':np.mean, 'Y':np.mean, 'tile':np.max}).reset_index()
        brc['X'] = [f"{x:.{args.precision}f}" for x in brc.X.values]
        brc['Y'] = [f"{x:.{args.precision}f}" for x in brc.Y.values]
        brc.sort_values(by = 'cRow', inplace=True)
        with open(brc_f, 'a') as wf:
            _ = wf.write('\n'.join((brc.cRow+n_unit+1).astype(str).values + '_' + brc.tile.astype(str) + '_' + brc.X.values + '_' + brc.Y.values)+'\n')

        n_hex = len(hex_dict)
        n_minib = n_hex // b_size
        print(f"{n_minib}, {n_hex} ({sub.cRow.max()}, {sub.shape[0]}), median count per unit {mid_ct}")
        if n_hex < b_size // 4:
            offs_y += 1
            continue
        grd_minib = list(range(0, n_hex, b_size))
        grd_minib[-1] = n_hex
        st_minib = 0
        n_minib = len(grd_minib) - 1

        while st_minib < n_minib:
            indx_minib = (sub.cRow >= grd_minib[st_minib]) & (sub.cRow < grd_minib[st_minib+1])
            npixel_minib = sum(indx_minib)
            offset = sub.loc[indx_minib, 'cRow'].min()
            nhex_minib = sub.loc[indx_minib, 'cRow'].max() - offset + 1

            mtx = coo_matrix((np.ones(npixel_minib, dtype=bool), (sub.loc[indx_minib, 'cRow'].values-offset, sub.loc[indx_minib, 'cCol'].values)), shape=(nhex_minib, N) ).tocsr() @ dge_mtx

            mtx.eliminate_zeros()
            r, c = mtx.nonzero()
            r = np.array(r,dtype=int) + n_unit + 1
            c = np.array(c,dtype=int) + 1
            n_unit += mtx.shape[0]
            mtx = pd.DataFrame({'i':c, 'j':r, 'v':mtx.data})
            mtx['i'] = mtx.i.astype(int)
            mtx['j'] = mtx.j.astype(int)
            mtx.to_csv(mtx_f, mode='a', sep=' ', index=False, header=False)
            st_minib += 1
            print(f"{st_minib}/{n_minib}. Wrote {n_unit} units so far.")

        print(f"Sliding offset {offs_x}, {offs_y}. Fit data with {n_unit} units.")
        offs_y += 1
    offs_y = 0
    offs_x += 1

_ = os.system("gzip -f " + brc_f)

mtx_header = args.output_path + "/matrix.header"
with open(mtx_header, 'w') as wf:
    line = "%%MatrixMarket matrix coordinate integer general\n%\n"
    line += " ".join([str(x) for x in [M, n_unit, T]]) + "\n"
    wf.write(line)

arg = " ".join(["cat",mtx_header,mtx_f,"|gzip -c > ", mtx_f+".gz"])
if os.system(arg) == 0:
    _ = os.system("rm " + mtx_f)
    _ = os.system("rm " + mtx_header)