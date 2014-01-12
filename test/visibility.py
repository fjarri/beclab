from __future__ import print_function, division

import itertools

import numpy

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import reikna.cluda as cluda

from beclab import *


def run_test(thr, stepper_cls, integration, no_losses=False, wigner=False):

    print()
    print(
        "*** Running " + stepper_cls.abbreviation +
        ", " + integration +
        ", wigner=" + str(wigner) +
        ", no_losses=" + str(no_losses) + " test")
    print()

    # Simulation parameters

    lattice_size = (8, 8, 64) # spatial lattice points
    trajectories = 16 if wigner else 1 # simulation paths
    interval = 0.12 # time interval
    samples = 200 # how many samples to take during simulation
    steps = samples * 100 # number of time steps (should be multiple of samples)
    gamma = 0.0 if no_losses else 0.2
    f_detuning = 37
    f_rabi = 350
    N = 55000
    state_dtype = numpy.complex128
    freqs = (97.6, 97.6, 11.96)
    components = [const.rb87_1_minus1, const.rb87_2_1]
    scattering = const.scattering_matrix(components, B=const.magical_field_Rb87_1m1_2p1)
    losses = [
        (gamma, (1, 0)),
        (gamma, (0, 1))]

    rng = numpy.random.RandomState(1234)

    # Create simulation objects
    potential = HarmonicPotential(state_dtype, freqs)
    system = System(components, scattering, potential=potential, losses=losses)
    grid = UniformGrid(lattice_size, box_for_tf(system, 0, N))

    gs_gen = ImaginaryTimeGroundState(thr, state_dtype, grid, system)
    integrator = Integrator(
        thr, state_dtype, grid, system,
        trajectories=trajectories, stepper_cls=stepper_cls,
        wigner=wigner, seed=rng.randint(0, 2**32-1))

    # Ground state
    psi = gs_gen([N, 0], E_diff=1e-7, E_conv=1e-9, sample_time=1e-5)
    axial_n_max = (
        (numpy.abs(psi.data.get()[0,0]) ** 2).sum((0, 1)) * grid.dxs[0] * grid.dxs[1]).max()

    # Initial noise
    if wigner:
        psi = psi.to_wigner_coherent(paths, seed=rng.randint(0, 2**32-1))

    # Prepare samplers
    bs = BeamSplitter(psi, f_detuning=f_detuning, f_rabi=f_rabi)
    n_sampler = PopulationSampler(psi, beam_splitter=bs, theta=numpy.pi / 2)
    ax_sampler = Density1DSampler(psi, beam_splitter=bs, theta=numpy.pi / 2)
    samplers = dict(N=n_sampler, axial_density=ax_sampler)

    # Integrate
    bs(psi, 0, numpy.pi / 2)
    if integration == 'fixed':
        result, info = integrator.fixed_step(
            psi, 0, interval, steps, samples=samples,
            samplers=samplers, convergence=['N'])
    elif integration == 'adaptive':
        result, info = integrator.adaptive_step(
            psi, 0, interval / samples, t_end=interval,
            weak_convergence=dict(N=1e-4), samplers=samplers)

    N_mean = result['N']
    N_err = result['N_stderr']
    density = result['axial_density']
    N_exact = N * numpy.exp(-gamma * result['time'] * 2)

    suffix = (
        ('_wigner' if wigner else '') +
        ('_no-losses' if no_losses else '') +
        '_' + stepper_cls.abbreviation +
        '_' + integration)

    # Plot density
    for comp in (0, 1):
        fig = plt.figure()
        s = fig.add_subplot(111)
        s.imshow(density[:,comp,:].T, interpolation='nearest', origin='lower', aspect='auto',
            extent=(0, interval) + (grid.xs[-1][0] * 1e6, grid.xs[-1][-1] * 1e6),
            vmin=0, vmax=axial_n_max)
        s.set_xlabel('$t$')
        s.set_ylabel('$x$')
        fig.savefig('visibility_density_' + str(comp) + suffix + '.pdf')
        plt.close(fig)

    fig = plt.figure()
    s = fig.add_subplot(111)
    pz = (density[:,1] - density[:,0]) / (density[:,1] + density[:,0])
    s.imshow(pz.T, interpolation='nearest', origin='lower', aspect='auto',
        extent=(0, interval) + (grid.xs[-1][0] * 1e6, grid.xs[-1][-1] * 1e6),
        vmin=-1, vmax=1)
    s.set_xlabel('$t$')
    s.set_ylabel('$x$')
    fig.savefig('visibility_density_Pz' + suffix + '.pdf')
    plt.close(fig)

    # Plot population
    fig = plt.figure()
    s = fig.add_subplot(111)
    s.plot(result['time'], N_mean[:,0], 'r-')
    s.plot(result['time'], N_mean[:,1], 'g-')
    s.plot(result['time'], N_mean.sum(1), 'b-')
    if wigner:
        s.plot(result['time'], N_mean.sum(1) + N_err.sum(1), 'b--')
        s.plot(result['time'], N_mean.sum(1) - N_err.sum(1), 'b--')
    s.plot(result['time'], N_exact, 'k--')
    s.set_ylim(0, N)
    s.set_xlabel('$t$')
    s.set_ylabel('$N$')
    fig.savefig('visibility_N' + suffix + '.pdf')
    plt.close(fig)

    # Plot used steps
    ts_start, ts_end, steps_used = map(numpy.array, zip(*info.steps))

    fig = plt.figure()
    s = fig.add_subplot(111)
    s.bar(ts_start, steps_used, width=(ts_end - ts_start))
    s.set_xlabel('$t$')
    s.set_ylabel('steps')
    fig.savefig('visibility_steps' + suffix + '.pdf')
    plt.close(fig)


if __name__ == '__main__':

    # Run integration
    api = cluda.ocl_api()
    thr = api.Thread.create()

    steppers = [
        CDIPStepper,
        CDStepper,
        RK4IPStepper,
        RK46NLStepper,
    ]

    integrations = [
        'fixed',
        'adaptive',
    ]

    for stepper_cls, integration in itertools.product(steppers, integrations):
        run_test(thr, stepper_cls, integration, no_losses=True, wigner=False)
        run_test(thr, stepper_cls, integration, wigner=False)
        if integration == 'fixed':
            run_test(thr, stepper_cls, integration, wigner=True)
