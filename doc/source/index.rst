******
BEClab
******

A framework for numerical simulations of trapped BEC behavior.

.. toctree::
   :maxdepth: 2



BEC-specific wrappers
=====================

.. py:module:: beclab

.. autoclass:: System

.. autofunction:: box_for_tf


Grids
-----

.. autoclass:: UniformGrid
    :members:
    :show-inheritance:

.. autoclass:: beclab.grid.Grid
    :members:


Potential
---------

.. autoclass:: beclab.bec.Potential
    :members:

.. autoclass:: HarmonicPotential
    :show-inheritance:


Cutoffs
-------

.. autoclass:: WavelengthCutoff
    :members:
    :show-inheritance:

.. autoclass:: beclab.cutoff.Cutoff
    :members:


Ground states
-------------

.. autoclass:: ThomasFermiGroundState
    :members: __call__

.. autoclass:: ImaginaryTimeGroundState
    :members: __call__


Integration
-----------

.. autoclass:: Integrator
    :members:


Wavefunctions
-------------

.. autodata:: REPR_CLASSICAL

.. autodata:: REPR_WIGNER

.. autodata:: REPR_POSITIVE_P

.. autoclass:: beclab.wavefunction.WavefunctionSetMetadata

.. autoclass:: WavefunctionSet
    :show-inheritance:


Beam splitter
-------------

.. autoclass:: BeamSplitter


Samplers
--------

.. automodule:: beclab.samplers
    :members:


Filters
--------

.. automodule:: beclab.filters
    :members:


Meters
------

.. automodule:: beclab.meters
    :members:
    :special-members:


Constants
---------

.. automodule:: beclab.constants
    :members:


******************
Indices and tables
******************

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
