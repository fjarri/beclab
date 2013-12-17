import numpy

from reikna.helpers import product
from reikna.cluda import dtypes, Module, Snippet, functions
from reikna.core import Computation, Parameter, Annotation, Transformation, Type

from reikna.fft import FFT
from reikna.pureparallel import PureParallel


def get_ksquared(shape, box):
    ks = [
        2 * numpy.pi * numpy.fft.fftfreq(size, length / size)
        for size, length in zip(shape, box)]

    if len(shape) > 1:
        full_ks = numpy.meshgrid(*ks, indexing='ij')
    else:
        full_ks = ks

    return sum([full_k ** 2 for full_k in full_ks])


def get_prop_iter(state_arr, drift, diffusion=None, dW_arr=None, iterations=3):

    real_dtype = dtypes.real_for(state_arr.dtype)
    if diffusion is not None:
        noise_dtype = dW_arr.dtype
    else:
        noise_dtype = real_dtype

    return PureParallel(
        [
            Parameter('output', Annotation(state_arr, 'o')),
            Parameter('input', Annotation(state_arr, 'i'))]
            + ([Parameter('dW', Annotation(dW_arr, 'i'))] if diffusion is not None else []) +
            [Parameter('t', Annotation(real_dtype)),
            Parameter('dt', Annotation(real_dtype))],
        """
        <%
            all_indices = ', '.join(idxs)
            components = drift.components
            if diffusion is not None:
                noise_sources = diffusion.noise_sources
            idx_args = ", ".join(idxs[1:])
            psi_args = ", ".join("psi_" + str(c) + "_tmp" for c in range(components))

            if diffusion is None:
                dW = None
        %>

        %for comp in range(components):
        ${output.ctype} psi_${comp} = ${input.load_idx}(${comp}, ${all_indices});
        ${output.ctype} psi_${comp}_tmp = psi_${comp};
        ${output.ctype} dpsi_${comp};
        %endfor

        %if diffusion is not None:
        %for ncomp in range(noise_sources):
        ${dW.ctype} dW_${ncomp} = ${dW.load_idx}(${comp}, ${all_indices});
        %endfor
        %endif

        %for i in range(iterations):

        %for comp in range(components):
        dpsi_${comp} =
            ${mul_cr}(
                ${mul_cr}(${drift.module}${comp}(
                    ${idx_args}, ${psi_args}, ${t} + ${dt} / 2), ${dt})
                %if diffusion is not None:
                %for ncomp in range(noise_sources):
                + ${mul_cn}(${diffusion.module}${comp}_${ncomp}(
                    ${idx_args}, ${psi_args}, ${t} + ${dt} / 2), dW_${ncomp})
                %endfor
                %endif
                , 0.5);
        %endfor

        %for comp in range(components):
        psi_${comp}_tmp = psi_${comp} + dpsi_${comp};
        %endfor

        %endfor

        %for comp in range(components):
        ${output.store_idx}(${comp}, ${all_indices}, psi_${comp}_tmp + dpsi_${comp});
        %endfor
        """,
        guiding_array=state_arr.shape[1:],
        render_kwds=dict(
            drift=drift,
            diffusion=diffusion,
            iterations=iterations,
            mul_cr=functions.mul(state_arr.dtype, real_dtype),
            mul_cn=functions.mul(state_arr.dtype, noise_dtype)))


class SSCDStepper(Computation):
    """
    Split step, central difference stepper.
    """

    def __init__(self, shape, box, drift, ensembles=1, kinetic_coeff=-0.5, diffusion=None):

        real_dtype = dtypes.real_for(drift.dtype)

        if diffusion is not None:
            assert diffusion.dtype == drift.dtype
            assert diffusion.components == drift.components
            self._noise = True
            dW_dtype = real_dtype if diffusion.real_noise else drift.dtype
            dW_arr = Type(dW_dtype, (diffusion.noise_sources, ensembles) + shape)
        else:
            dW_arr = None
            self._noise = False

        state_arr = Type(drift.dtype, (drift.components, ensembles) + shape)

        Computation.__init__(self,
            [Parameter('output', Annotation(state_arr, 'o')),
            Parameter('input', Annotation(state_arr, 'i'))]
            + ([Parameter('dW', Annotation(dW_arr, 'i'))] if self._noise else []) +
            [Parameter('t', Annotation(real_dtype)),
            Parameter('dt', Annotation(real_dtype))])

        ksquared = get_ksquared(shape, box)
        self._kprop = (-ksquared * kinetic_coeff / 2).astype(real_dtype)
        kprop_trf = Transformation(
            [
                Parameter('output', Annotation(state_arr, 'o')),
                Parameter('input', Annotation(state_arr, 'i')),
                Parameter('kprop', Annotation(self._kprop, 'i')),
                Parameter('dt', Annotation(real_dtype))],
            """
            ${kprop.ctype} kprop = ${kprop.load_idx}(${', '.join(idxs[2:])});
            ${output.ctype} kprop_coeff = ${polar_unit}(kprop * ${dt});
            ${output.store_same}(${mul}(${input.load_same}, kprop_coeff));
            """,
            render_kwds=dict(
                mul=functions.mul(state_arr.dtype, state_arr.dtype),
                polar_unit=functions.polar_unit(real_dtype)))

        self._fft = FFT(state_arr, axes=range(2, len(state_arr.shape)))
        self._fft_with_kprop = FFT(state_arr, axes=range(2, len(state_arr.shape)))
        self._fft_with_kprop.parameter.output.connect(
            kprop_trf, kprop_trf.input,
            output_prime=kprop_trf.output, kprop=kprop_trf.kprop, dt=kprop_trf.dt)

        self._prop_iter = get_prop_iter(state_arr, drift, diffusion=diffusion, dW_arr=dW_arr)

    def _add_kprop(self, plan, output, input_, kprop_device, dt):
        temp = plan.temp_array_like(output)
        plan.computation_call(self._fft_with_kprop, temp, kprop_device, dt, input_)
        plan.computation_call(self._fft, output, temp, inverse=True)

    def _build_plan(self, plan_factory, device_params, *args):

        if self._noise:
            output, input_, dW, t, dt = args
        else:
            output, input_, t, dt = args

        plan = plan_factory()

        kprop_device = plan.persistent_array(self._kprop)

        # psi_I = prop_L_half_dt(input_)
        psi_I = plan.temp_array_like(input_)
        self._add_kprop(plan, psi_I, input_, kprop_device, dt)

        # psi_N = prop_iter(psi_I)
        psi_N = plan.temp_array_like(input_)
        if self._noise:
            plan.computation_call(self._prop_iter, psi_N, psi_I, dW, t, dt)
        else:
            plan.computation_call(self._prop_iter, psi_N, psi_I, t, dt)

        # output = prop_L_half_dt(psi_N)
        self._add_kprop(plan, output, psi_N, kprop_device, dt)

        return plan
