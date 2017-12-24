from .. import TimeChunkedProperty
from . import pynbody_handler_module

import numpy as np

class StarFormHistogram(TimeChunkedProperty):
    works_with_handler = pynbody_handler_module.PynbodyOutputSetHandler
    requires_particle_data = True

    @classmethod
    def name(self):
        return "SFR_histogram"

    def calculate(self, halo, existing_properties):
        M,_ = np.histogram(halo.st['tform'].in_units("Gyr"),weights=halo.st['massform'].in_units("Msol"),bins=self.nbins,range=(0,self.tmax_Gyr))
        t_now = halo.properties['time'].in_units("Gyr")
        M/=self.delta_t
        M = M[self.store_slice(t_now)]

        return M

    @classmethod
    def reassemble(cls, *options):
        reassembled = TimeChunkedProperty.reassemble(*options)
        return reassembled/1e9 # Msol per Gyr -> Msol per yr