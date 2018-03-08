from __future__ import division
import pandas as pd
import numpy as np
import h5py
from detection_localisation.detect import detectData
from matplotlib import pyplot as plt
# from sklearn.cluster import MeanShift # joblib things are broken
from clustering.mean_shift_ import MeanShift
from sklearn.decomposition import PCA
from os.path import splitext


class Detection(object):
    """
    This class provides a simple interface to the detection, localisation and
    clustering of spike data from dense multielectrode arrays according to the
    methods described in the following papers:

    Muthmann, J. O., Amin, H., Sernagor, E., Maccione, A., Panas, D.,
    Berdondini, L., ... & Hennig, M. H. (2015). Spike detection for large neural
    populations using high density multielectrode arrays.
    Frontiers in neuroinformatics, 9.

    Hilgen, G., Sorbaro, M., Pirmoradian, S., Muthmann, J. O., Kepiro, I. E.,
    Ullo, S., ... & Hennig, M. H. (2017). Unsupervised spike sorting for
    large-scale, high-density multielectrode arrays.
    Cell reports, 18(10), 2521-2532.

    Usage:
    1. call the constructor with a single argument -- a NeuralProbe object:
        HS = herdingspikes(Probe)
    2. You can now load your data in three ways: with LoadDetected()
    (automatically loads ProcessedSpikes); with DetectFromRaw (takes a path
    to the raw data and all detection parameters) or with LoadH5 (takes a
    previously saved instance of this class)
    """

    def __init__(self, probe, to_localize, cutout_start, cutout_end, threshold,
                 maa=0, maxsl=12, minsl=3, ahpthr=0, tpre=1.0, tpost=2.2,
                 out_file_name="ProcessedSpikes.bin", save_all=False):
        self.probe = probe
        # self.shapecache = None
        # self.HasFeatures = False
        self.to_localize = to_localize
        self.cutout_start = cutout_start
        self.cutout_end = cutout_end
        self.cutout_length = cutout_start + cutout_end + 1
        self.threshold = threshold
        self.maa = maa
        self.maxsl = maxsl
        self.minsl = minsl
        self.ahpthr = ahpthr
        self.tpre = tpre
        self.tpost = tpost
        self.out_file_name = out_file_name
        self.save_all = save_all

    def LoadDetected(self):
        """
        Reads a binary file with spikes detected with the DetectFromRaw() method
        """

        sp_flat = np.memmap(self.out_file_name, dtype=np.int32, mode="r")
        assert sp_flat.shape[0] // (self.cutout_length + 5) is not \
            sp_flat.shape[0] / (self.cutout_length + 5), \
            "spike data has wrong dimensions"  # ???
        shapecache = sp_flat.reshape((-1, self.cutout_length + 5))
        self.spikes = pd.DataFrame({'ch': shapecache[:, 0],
                                    't': shapecache[:, 1],
                                    'Amplitude': shapecache[:, 2],
                                    'x': shapecache[:, 3] / 1000,
                                    'y': shapecache[:, 4] / 1000,
                                    'Shape': list(shapecache[:, 5:])
                                    }, copy=False)
        self.IsClustered = False
        print('Detected and read ' + str(self.spikes.shape[0]) + ' spikes.')

    def DetectFromRaw(self, load=False):
        """
        This function is a wrapper of the C function `detectData`. It takes
        the raw data file, performs detection and localisation, saves the result
        to `ProcessedSpikes` and loads the latter into memory by calling
        `LoadDetected`.

        Arguments:
        file_name -- the path to the raw data file.
        to_localize
        cutout_start
        cutout_end
        threshold
        maa
        maxsl
        minsl
        ahpthr
        out_file_name
        load -- load the detected spikes when finished
        """
        detectData(self.probe, str.encode(self.out_file_name),
                   self.to_localize, self.probe.fps, self.threshold,
                   self.cutout_start, self.cutout_end,
                   self.maa, self.maxsl, self.minsl, self.ahpthr,
                   self.tpre, self.tpost, self.save_all)
        if load:
            # reload data into memory
            self.LoadDetected()

    def PlotTracesChannels(self, eventid, ax=None, window_size=200):
        """
        Draw a figure with an electrode and its neighbours, showing the raw
        traces and events. Note that this requires loading the raw data in
        memory again.

        Arguments:
        eventid -- centers, spatially and temporally, the plot to a specific
        event id.
        ax -- a matplotlib axes object where to draw. Defaults to current axis.
        window_size -- number of samples shown around a spike
        cutout_start -- n. frames recorded before the spike peak in the cutout
        """
        pos, neighs = self.probe.positions, self.probe.neighbors

        event = self.spikes.loc[eventid]
        print("Spike detected at channel: ", event.ch)
        print("Spike detected at frame: ", event.t)
        cutlen = len(event.Shape)
        assert window_size > cutlen, "window_size is too small"
        dst = np.abs(pos[event.ch][0] - pos[neighs[event.ch]][:, 0])
        interdistance = np.min(dst[dst > 0])
        if ax is None:
            ax = plt.gca()

        # scatter of the large grey balls for electrode location
        plt.scatter(np.array(pos)[neighs[event.ch], 0],
                    np.array(pos)[neighs[event.ch], 1],
                    s=1600, alpha=0.2)
        x = pos[[neighs[event.ch], 0]]
        y = pos[[neighs[event.ch], 1]]
        for i, txt in enumerate(neighs[event.ch]):
            ax.annotate(txt, (x[i] + 1, y[i] + 3))

        ws = window_size // 2
        t1 = np.max((0, event.t - ws))
        t2 = event.t + ws
        scale = interdistance/110.
        trange = (np.arange(t1, t2)-event.t)*scale
        start_bluered = event.t-t1 - self.cutout_start
        trange_bluered = trange[start_bluered:start_bluered+cutlen]
        trange_bluered = np.arange(-self.cutout_start,
                                   -self.cutout_start+cutlen)*scale

        data = self.probe.Read(t1, t2).reshape((t2-t1, self.probe.num_channels))
        for n in neighs[event.ch]:
            if n not in self.probe.masked_channels:
                plt.plot(pos[n][0] + trange,
                         pos[n][1] + data[:, n]*scale, 'gray')
                plt.plot(pos[n][0] + trange_bluered,
                         pos[n][1] + data[start_bluered:start_bluered+cutlen,
                         n]*scale, 'b')
            else:
                plt.plot(pos[n][0] + trange,
                         pos[n][1] + data[:, n]*scale, 'gray')
                plt.plot(pos[n][0] + trange_bluered,
                         pos[n][1] + data[start_bluered:start_bluered+cutlen,
                         n]*scale, 'g')

        plt.plot(pos[event.ch][0] + trange_bluered,
                 pos[event.ch][1] + event.Shape * scale, 'r')
        plt.scatter(event.x, event.y, s=80, c='r')

    def PlotDensity(self, binsize=1., invert=False, ax=None):
        raise NotImplementedError()
        if ax is None:
            ax = plt.gca()
        x, y = self.spikes.x, self.spikes.y
        if invert:
            x, y = y, x
        binsx = np.arange(x.min(), x.max(), binsize)
        binsy = np.arange(y.min(), y.max(), binsize)
        h, xb, yb = np.histogram2d(x, y, bins=[binsx, binsy])
        ax.imshow(np.log10(h), extent=[xb.min(), xb.max(), yb.min(), yb.max()],
                  interpolation='none', origin='lower')
        return h, xb, yb

    def PlotAll(self, invert=False, ax=None, max_show=200000, **kwargs):
        """
        Plots all the spikes currently stored in the class, in (x, y) space.

        Arguments:
        invert -- (boolean, optional) if True, flips x and y
        ax -- a matplotlib axes object where to draw. Defaults to current axis.
        max_show -- maximum number of spikes to show
        **kwargs -- additional arguments are passed to pyplot.scatter
        """
        if ax is None:
            ax = plt.gca()
        x, y = self.spikes.x, self.spikes.y
        if invert:
            x, y = y, x
        if self.spikes.shape[0] > max_show:
            inds = np.random.choice(
                self.spikes.shape[0], max_show, replace=False)
            print('We have ' + str(self.spikes.shape[0]) +
                  ' spikes, only showing ' + str(max_show))
        else:
            inds = np.arange(self.spikes.shape[0])
        ax.scatter(x[inds], y[inds], **kwargs)
        return ax


class Clustering(object):
    def __init__(self, arg1, cutout_length=None):
        if type(arg1) == str:  # case arg1 is a single filename
            arg1 = [arg1]

        if type(arg1) == list:  # case arg1 is a list of filenames
            for i, f in enumerate(arg1):
                filetype = splitext(f)[-1]
                not_first_file = i > 0
                if filetype == ".hdf5":
                    self.LoadHDF5(f, append=not_first_file)
                elif filetype == ".bin":
                    if cutout_length is None:
                        raise ValueError(
                            "You must pass cutout_length for .bin files.")
                    self.LoadBin(f, cutout_length, append=not_first_file)
                else:
                    raise IOError("File format unknown. Expected .hdf5 or .bin")
        else:  # we suppose arg1 is an instance of Detection
            try:  # see if LoadDetected was run
                self.spikes = arg1.spikes
            except NameError:
                arg1.LoadDetected()
                self.spikes = arg1.spikes
            self.filelist = [arg1.out_file_name]
            self.expinds = [0]
            self.IsClustered = False

    def CombinedClustering(self, alpha, clustering_algorithm=MeanShift,
                           **kwargs):
        """
        Performs PCA on the available spike shapes, and clusters spikes based
        on their (x, y) location and on the principal components of the shape.
        Cluster memberships are available as self.spikes.cl.
        Cluster information is available in the self.clusters dataframe.

        Arguments:
        alpha -- the weight given to PCA components, relative to spatial
        components clustering_algorithm -- a sklearn.cluster class, defaults to
        sklearn.cluster.MeanShift. sklearn.cluster.DBSCAN was also tested.
        pca_ncomponents -- number of PCA components to be considered (def. 2).
        pca_whiten -- whiten option of the PCA algorithm.
        **kwargs -- additional arguments are passed to the clustering class.
        This may include n_jobs > 1 for parallelisation.
        """
        try:
            fourvec = np.vstack(([self.spikes.x], [self.spikes.y],
                                 alpha * self.features.T)).T
        except AttributeError:
            fourvec = np.vstack(([self.spikes.x], [self.spikes.y])).T
            print("Warning: no PCA or other features available, location only!")

        print('Clustering...')
        clusterer = clustering_algorithm(**kwargs)
        clusterer.fit(fourvec)
        self.spikes['cl'] = clusterer.labels_
        self.NClusters = len(np.unique(clusterer.labels_))
        print("Number of estimated clusters:", self.NClusters)
        in_cl = []
        for i in np.arange(self.NClusters):
            in_cl.append(list(np.where(self.spikes.cl == i)[0]))
        self.fourvec = fourvec
        centers = np.asarray([np.mean(fourvec[cl], axis=0) for cl in in_cl])
        self.centerz = centers
        self.in_cl = in_cl
        dic_cls = {'ctr_x': centers[:, 0],
                   'ctr_y': centers[:, 1],
                   'Color': 1. * np.random.permutation(
            self.NClusters) / self.NClusters,
            'Size': [len(cl) for cl in in_cl],
            'AvgAmpl': [np.mean(self.spikes.Amplitude[cl])
                        for cl in in_cl]}
        self.clusters = pd.DataFrame(dic_cls)
        self.IsClustered = True

    def ShapePCA(self, pca_ncomponents=2, pca_whiten=True, chunk_size=1000000):
        pca = PCA(n_components=pca_ncomponents, whiten=pca_whiten)
        if self.spikes.shape[0] > 1e6:
            print("Fitting PCA using 1e6 out of",
                  self.spikes.shape[0], "spikes...")
            inds = np.random.choice(self.spikes.shape[0], int(1e6),
                                    replace=False)
            pca.fit(np.array(list(self.spikes.Shape[inds])))
        else:
            print("Fitting PCA using", self.spikes.shape[0], "spikes...")
            pca.fit(np.array(list(self.spikes.Shape)))
        self.pca = pca
        _pcs = np.empty((self.spikes.shape[0], pca_ncomponents))
        for i in range(self.spikes.shape[0] // chunk_size + 1):
            _pcs[i*chunk_size:(i+1)*chunk_size, :] = pca.transform(np.array(
                list(self.spikes.Shape[i * chunk_size:(i + 1) * chunk_size])))
        self.features = _pcs

        return _pcs

    def _savesinglehdf5(self, filename, limits, compression, sampling):
        if limits is not None:
            print("DOESN'T WORK")
            spikes = self.spikes[limits[0]:limits[1]]
        else:
            spikes = self.spikes
        g = h5py.File(filename, 'w')
        g.create_dataset("data", data=np.vstack(
            (spikes.x, spikes.y)))
        if sampling is not None:
            g.create_dataset("Sampling", data=sampling)
        g.create_dataset("times", data=spikes.t)
        if self.IsClustered:
            g.create_dataset("centres", data=self.centerz.T)
            g.create_dataset("cluster_id", data=spikes.cl)
        g.create_dataset("exp_inds", data=self.expinds)
        # this is still a little slow (and perhaps memory intensive)
        # but I have not found a better way:
        cutout_length = spikes.Shape[0].size
        sh_tmp = np.empty((cutout_length, spikes.Shape.size),
                          dtype=int)
        for i in range(spikes.Shape.size):
            sh_tmp[:, i] = spikes.Shape[i]  # TODO ???????
        g.create_dataset("shapes", data=sh_tmp, compression=compression)
        g.close()

    def SaveHDF5(self, filename, compression=None, sampling=None):
        """
        Saves data, cluster centres and ClusterIDs to a hdf5 file.
        Offers compression of the shapes, 'lzf'
        appears a good trade-off between speed and performance.

        If filename is a single name, then all will be saved to a single file.
        If filename is a list of names of the same length as the number of
        experiments, one file per experiment will be saved.
        """
        print("Not tested, hope it works")
        if type(filename) == str:
            self._savesinglehdf5(filename, None, compression, sampling)
        elif type(filename) == list:
            if len(filename) != len(self.expinds):
                raise ValueError("Names list length does not correspond.")
            expinds = self.expinds + [len(self.spikes)]
            for i, f in enumerate(filename):
                self._savesinglehdf5(f, [expinds[i], expinds[i+1]],
                                     compression, sampling)
        else:
            raise ValueError("filename not understood")

    def LoadHDF5(self, filename, append=False, compute_amplitudes=False,
                 chunk_size=500000, compute_cluster_sizes=False):
        """
        Load data, cluster centres and ClusterIDs from a hdf5 file created with
        HS1.
        """
        g = h5py.File(filename, 'r')
        print('Reading from ' + filename)

        print("Creating memmapped cache for shapes, reading in chunks, " +
              "converting to integer...")
        shapecache = np.memmap(
            "tmp.bin", dtype=np.int32, mode="w+", shape=g['shapes'].shape[::-1])
        for i in range(g['shapes'].shape[1] // chunk_size + 1):
            tmp = (1000 * np.transpose(g['shapes'][:, i *
                   chunk_size:(i+1)*chunk_size])).astype(np.int32)
            inds = np.where(tmp > 20000)[0]
            tmp[inds] = 0
            print('Found ' + str(len(inds)) +
                  ' data points out of linear regime in chunk '+str(i+1))
            shapecache[i * chunk_size:(i + 1) * chunk_size] = tmp[:]

        self.cutout_length = shapecache.shape[1]

        spikes = pd.DataFrame(
            {'ch': np.zeros(g['times'].shape[0], dtype=int),
             't': g['times'],
             'Amplitude': np.zeros(g['times'].shape[0], dtype=int),
             'x': g['data'][0, :],
             'y': g['data'][1, :],
             'Shape': list(shapecache)
             }, copy=False)

        if 'centres' in list(g.keys()):
            self.centerz = g['centres'].value.T
            self.NClusters = len(self.centerz)
            spikes['cl'] = g['cluster_id']

            if compute_amplitudes:
                print('Computing amplitudes...')
                self.spikes.Amplitude = [np.min(s) for s in shapecache]
                _avgAmpl = [np.mean(self.spikes.Amplitude[cl])
                            for cl in range(self.NClusters)]
            else:
                _avgAmpl = np.zeros(self.NClusters, dtype=int)

            if compute_cluster_sizes:
                _cls = [np.sum(self.spikes.cl == cl)
                        for cl in range(self.NClusters)]
            else:
                _cls = np.zeros(self.NClusters, dtype=int)

            dic_cls = {'ctr_x': self.centerz[:, 0],
                       'ctr_y': self.centerz[:, 1],
                       'Color': 1. * np.random.permutation(
                                    self.NClusters)/self.NClusters,
                       'Size': _cls,
                       'AvgAmpl': _avgAmpl}

            self.clusters = pd.DataFrame(dic_cls)
            self.IsClustered = True
        else:
            self.IsClustered = False

        if append:
            self.expinds.append(len(self.spikes))
            self.spikes = pd.concat([self.spikes, spikes], ignore_index=True)
            self.filelist.append(filename)
        else:
            self.spikes = spikes
            self.expinds = [0]
            self.filelist = [filename]

        g.close()

    def LoadBin(self, filename, cutout_length, append=False):
        """
        Reads a binary file with spikes detected with the DetectFromRaw() method
        """

        sp_flat = np.memmap(filename, dtype=np.int32, mode="r")
        assert sp_flat.shape[0] // (cutout_length + 5) is not \
            sp_flat.shape[0] / (cutout_length + 5), \
            "spike data has wrong dimensions"  # ???
        # 5 here are the non-shape data columns
        shapecache = sp_flat.reshape((-1, cutout_length + 5))
        spikes = pd.DataFrame({
            'ch': shapecache[:, 0],
            't': shapecache[:, 1],
            'Amplitude': shapecache[:, 2],
            'x': shapecache[:, 3] / 1000,
            'y': shapecache[:, 4] / 1000,
            'Shape': list(shapecache[:, 5:])
            }, copy=False)
        self.IsClustered = False

        if append:
            self.expinds.append(len(self.spikes)+1)
            self.spikes = pd.concat([self.spikes, spikes], ignore_index=True)
            self.filelist.append(filename)
        else:
            self.spikes = spikes
            self.expinds = [0]
            self.filelist = [filename]

    def PlotShapes(self, units, nshapes=100, ncols=4, ax=None, ylim=None):
        """
        Plot a sample of the spike shapes contained in a given set of clusters
        and their average.

        Arguments:
        units -- a list of the cluster IDs to be considered.
        nshapes -- the number of shapes to plot (default 100).
        ncols -- the number of columns under which to distribute the plots.
        ax -- a matplotlib axis object (defaults to current axis).
        """
        nrows = np.ceil(len(units) / ncols)
        if ax is None:
            plt.figure(figsize=(3 * ncols, 3 * nrows))
        cutouts = np.array(list(self.spikes.Shape))

        # all this is to determine suitable ylims TODO probe should provide
        if ylim is None:
            meanshape = np.mean(cutouts, axis=0)
            maxy, miny = meanshape.max(), meanshape.min()
            varshape = np.var(cutouts, axis=0)
            varmin = varshape[np.argmin(meanshape)]
            varmax = varshape[np.argmax(meanshape)]
            maxy += 4. * np.sqrt(varmax)
            miny -= 2. * np.sqrt(varmin)
            ylim = [miny, maxy]

        for i, cl in enumerate(units):
            inds = np.where(self.spikes.cl == cl)[0]
            if ax is None:
                plt.subplot(nrows, ncols, i + 1)
            plt.plot(cutouts[inds[:100], :].T, 'gray', alpha=0.3)
            plt.plot(np.mean(cutouts[inds, :], axis=0),
                     c=plt.cm.hsv(self.clusters.Color[cl]), lw=4)
            plt.ylim(ylim)
            plt.title("Cluster " + str(cl))

    def PlotAll(self, invert=False, show_labels=False, ax=None,
                max_show=200000, **kwargs):
        """
        Plots all the spikes currently stored in the class, in (x, y) space.
        If clustering has been performed, each spike is coloured according to
        the cluster it belongs to.

        Arguments:
        invert -- (boolean, optional) if True, flips x and y
        show_labels -- (boolean, optional) if True, annotates each cluster
        centre with its cluster ID.
        ax -- a matplotlib axes object where to draw. Defaults to current axis.
        max_show -- maximum number of spikes to show
        **kwargs -- additional arguments are passed to pyplot.scatter
        """
        if ax is None:
            ax = plt.gca()
        x, y = self.spikes.x, self.spikes.y
        if invert:
            x, y = y, x
        if self.spikes.shape[0] > max_show:
            inds = np.random.choice(
                self.spikes.shape[0], max_show, replace=False)
            print('We have ' + str(self.spikes.shape[0]) +
                  ' spikes, only showing ' + str(max_show))
        else:
            inds = np.arange(self.spikes.shape[0])
        c = plt.cm.hsv(self.clusters.Color[self.spikes.cl])
        ax.scatter(x[inds], y[inds], c=c[inds], **kwargs)
        if show_labels and self.IsClustered:
            ctr_x, ctr_y = self.clusters.ctr_x, self.clusters.ctr_y
            if invert:
                ctr_x, ctr_y = ctr_y, ctr_x
            for cl in range(self.NClusters):  # TODO why is this here
                if ~np.isnan(ctr_y[cl]):  # hack, why NaN positions in DBScan?
                    ax.annotate(str(cl), [ctr_x[cl], ctr_y[cl]], fontsize=16)
                    # seems this is a problem when zooming with x/ylim
        return ax
