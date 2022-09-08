"""Utilities for manipulating the torch.Graph object."""


import dataclasses
import numbers
import re
from typing import Any, Dict, Iterable, Iterator, List, Tuple, Union

import torch
from torch import _C
from torch._C import _onnx as _C_onnx

from torch.onnx import _deprecation
from torch.onnx._globals import GLOBALS
from torch.onnx._internal import _beartype

_ATTR_PATTERN = re.compile("^(.+)_(([ifstgz])|(ty))$")


@dataclasses.dataclass
class GraphContext:
    """Extra context for symbolic functions with all methods from torch.Graph.

    Attributes:
        graph: The graph being constructed.
        opset: The opset version.
        original_node: Current node that is being converted from.
        onnx_block: Current ONNX block that converted nodes are being appended to.
        params_dict: Mapping from graph initializer name to IValue.
    """

    graph: _C.Graph
    opset: int
    original_node: _C.Node
    onnx_block: _C.Block
    params_dict: Dict[str, "_C.IValue"]
    # TODO(justinchuby): What should we call env?

    def op(
        self,
        opname: str,
        *raw_args: Union[torch.Tensor, _C.Value],
        outputs: int = 1,
        **kwargs,
    ) -> Union[_C.Value, Tuple[_C.Value, ...]]:
        """Creates an ONNX operator "opname", taking "args" as inputs and attributes "kwargs".

        The set of operators and the inputs/attributes they take
        is documented at https://github.com/onnx/onnx/blob/master/docs/Operators.md

        This function is monkey-patched onto Graph.

        Args:
            g: The Torch graph.
            opname: The ONNX operator name, e.g., `Abs` or `Add`, or an operator qualified
                with a namespace, e.g., `aten::add`.
            raw_args: The inputs to the operator; usually provided
                as arguments to the `symbolic` definition.
            outputs: The number of outputs this operator returns.
                By default an operator is assumed to return a single output.
                If `outputs` is greater than one, this functions returns a tuple
                of output `Node`, representing each output of the ONNX operator
                in positional.
            kwargs: The attributes of the ONNX operator, whose keys are named
                according to the following convention: `alpha_f` indicates
                the `alpha` attribute with type `f`.  The valid type specifiers are
                `f` (float), `i` (int), `s` (string) or `t` (Tensor).  An attribute
                specified with type float accepts either a single float, or a
                list of floats (e.g., you would say `dims_i` for a `dims` attribute
                that takes a list of integers).

        Returns:
            The node representing the single output of this operator (see the `outputs`
            keyword argument for multi-return nodes).
        """
        return graph_op(self.graph, opname, *raw_args, outputs=outputs, **kwargs)

    def at(
        self, operator: str, *args, overload_name: str = "", **kwargs
    ) -> Union[_C.Value, Tuple[_C.Value, ...]]:
        from torch.onnx._internal import torch_graph

        return aten_op(
            self.graph, operator, *args, overload_name=overload_name, **kwargs
        )

    # Relay methods from _C.Graph for compatibility with symbolic functions that expect
    # a _C.Graph
    def inputs(self) -> List[_C.Value]:
        return self.graph.inputs()

    def outputs(self) -> List[_C.Value]:
        return self.graph.outputs()

    def nodes(self) -> Iterator[_C.Node]:
        return self.graph.nodes()

    def param_node(self) -> _C.Node:
        return self.graph.param_node()

    def return_node(self) -> _C.Node:
        return self.graph.return_node()

    def addInput(self, name: str) -> _C.Value:
        return self.graph.addInput(name)

    def eraseInput(self, i: int) -> None:
        return self.graph.eraseInput(i)

    def registerOutput(self, n: _C.Value) -> int:
        return self.graph.registerOutput(n)

    def eraseOutput(self, i: int) -> None:
        return self.graph.eraseOutput(i)

    def create(self, name: str, args, num_outputs: int) -> _C.Node:
        return self.graph.create(name, args, num_outputs)

    def appendNode(self, n: _C.Node) -> _C.Node:
        return self.graph.appendNode(n)

    def prependNode(self, n: _C.Node) -> _C.Node:
        return self.graph.prependNode(n)

    def insertNode(self, n: _C.Node) -> _C.Node:
        return self.graph.insertNode(n)

    def block(self) -> _C.Block:
        return self.graph.block()

    def lint(self) -> None:
        return self.graph.lint()

    def setInsertPoint(self, n: Union[_C.Block, _C.Node]) -> None:
        return self.graph.setInsertPoint(n)

    def insert_point_guard(self, n: Union[_C.Block, _C.Node]):
        return self.graph.insert_point_guard(n)

    def insertPoint(self) -> _C.Node:
        return self.graph.insertPoint()

    def insertGraph(self, callee: _C.Graph, inputs: List[_C.Value]) -> List[_C.Value]:
        return self.graph.insertGraph(callee, inputs)

    def makeMultiOutputIntoTuple(self) -> None:
        return self.graph.makeMultiOutputIntoTuple()


@_beartype.beartype
def graph_op(
    g: _C.Graph,
    opname: str,
    *raw_args: Union[torch.Tensor, _C.Value],
    outputs: int = 1,
    **kwargs,
) -> Union[_C.Value, Tuple[_C.Value, ...]]:
    """Creates an ONNX operator "opname", taking "args" as inputs and attributes "kwargs".

    The set of operators and the inputs/attributes they take
    is documented at https://github.com/onnx/onnx/blob/master/docs/Operators.md

    This function is monkey-patched onto Graph.

    Args:
        g: The Torch graph.
        opname: The ONNX operator name, e.g., `Abs` or `Add`, or an operator qualified
            with a namespace, e.g., `aten::add`.
        raw_args: The inputs to the operator; usually provided
            as arguments to the `symbolic` definition.
        outputs: The number of outputs this operator returns.
            By default an operator is assumed to return a single output.
            If `outputs` is greater than one, this functions returns a tuple
            of output `Node`, representing each output of the ONNX operator
            in positional.
        kwargs: The attributes of the ONNX operator, whose keys are named
            according to the following convention: `alpha_f` indicates
            the `alpha` attribute with type `f`.  The valid type specifiers are
            `f` (float), `i` (int), `s` (string) or `t` (Tensor).  An attribute
            specified with type float accepts either a single float, or a
            list of floats (e.g., you would say `dims_i` for a `dims` attribute
            that takes a list of integers).

    Returns:
        The node representing the single output of this operator (see the `outputs`
        keyword argument for multi-return nodes).
    """
    # Filter out None attributes, this can be convenient client side because
    # now they can pass through None attributes, and have them not show up
    kwargs = {k: v for k, v in kwargs.items() if v is not None}

    args = [_const_if_tensor(g, arg) for arg in raw_args]

    if "::" in opname:
        namespace, op = opname.split("::")
    else:
        namespace = "onnx"
        op = opname

    n = g.insertNode(_new_node(g, namespace, op, outputs, *args, **kwargs))

    if GLOBALS.onnx_shape_inference:
        # Import utils to get _params_dict because it is a global that is accessed by c++ code
        from torch.onnx import utils

        _C._jit_pass_onnx_node_shape_type_inference(
            n, utils._params_dict, GLOBALS.export_onnx_opset_version
        )

    if outputs == 1:
        return n.output()
    return tuple(n.outputs())


@_beartype.beartype
def _const_if_tensor(g: _C.Graph, arg):
    if arg is None:
        return arg
    if isinstance(arg, _C.Value):
        return arg
    return graph_op(g, "Constant", value_z=arg)


# Generate an ONNX ATen op node.
@_beartype.beartype
def aten_op(
    g: _C.Graph, operator: str, *args, overload_name: str = "", **kwargs
) -> Union[_C.Value, Tuple[_C.Value, ...]]:
    return graph_op(
        g,
        "aten::ATen",
        *args,
        operator_s=operator,
        overload_name_s=overload_name,
        **kwargs,
    )


@_beartype.beartype
def block_op(b: _C.Block, opname: str, *args: _C.Value, **kwargs):
    if "::" in opname:
        aten = False
        ns_opname = opname
    else:
        aten = kwargs.pop("aten", False)
        ns = "aten" if aten else "onnx"
        ns_opname = ns + "::" + opname
    n = b.addNode(ns_opname, args)
    for k, v in sorted(kwargs.items()):
        if k == "inplace":
            continue
        _add_attribute(n, k, v, aten=aten)
    outputs = tuple(n.outputs())
    if len(outputs) == 1:
        return n.output()
    return outputs


@_beartype.beartype
def _new_node(
    g: _C.Graph, namespace: str, op: str, outputs: int, *args: _C.Value, **kwargs
) -> _C.Node:
    """Creates a new node in the graph.

    Args:
        g: The graph to create the operator on.
        namespace: The namespace of the operator. E.g., "aten", "onnx".
        op: The name of the operator to create.
        outputs: The number of the outputs of the node.

    Returns:
        The new node.
    """
    aten = kwargs.pop("aten", False)
    node = g.create(f"{namespace}::{op}", args, outputs)
    for k, v in sorted(kwargs.items()):
        if k == "inplace":
            continue
        _add_attribute(node, k, v, aten=aten)
    return node


@_beartype.beartype
def _is_onnx_list(value):
    return (
        not isinstance(value, torch._six.string_classes)
        and not isinstance(value, torch.Tensor)
        and isinstance(value, Iterable)
    )


@_beartype.beartype
def _scalar(x: torch.Tensor):
    """Convert a scalar tensor into a Python value."""
    assert x.numel() == 1
    return x[0]


@_beartype.beartype
def _is_caffe2_aten_fallback() -> bool:
    return (
        GLOBALS.operator_export_type == _C_onnx.OperatorExportTypes.ONNX_ATEN_FALLBACK
        and _C_onnx._CAFFE2_ATEN_FALLBACK
    )


@_beartype.beartype
def _add_attribute(node: _C.Node, key: str, value: Any, aten: bool):
    r"""Initializes the right attribute based on type of value."""
    m = _ATTR_PATTERN.match(key)
    if m is None:
        raise ValueError(
            f"Invalid attribute specifier '{key}' names "
            " must be suffixed with type, e.g. 'dim_i' or 'dims_i'"
        )
    name, kind = m.group(1), m.group(2)
    if _is_onnx_list(value):
        kind += "s"

    if aten and _is_caffe2_aten_fallback():
        if isinstance(value, torch.Tensor):
            # Caffe2 proto does not support tensor attribute.
            if value.numel() > 1:
                raise ValueError("Should not pass tensor attribute")
            value = _scalar(value)
            if isinstance(value, float):
                kind = "f"
            else:
                kind = "i"
    return getattr(node, f"{kind}_")(name, value)


# TODO(#76254): Remove the deprecated function.
@_deprecation.deprecated(
    "1.13", "1.14", "Use 'g.op()' to create a constant node instead."
)
@_beartype.beartype
def graph_constant(
    g,
    value,
    dims,
    type_: str,
    *args,
    **kwargs,
):
    """This helper function can create either constant tensor or constant scalar.

    If dims is None or 0 or [0], generate a 0-d tensor (scalar).
    """
    assert isinstance(value, numbers.Number)
    assert type_ is not None
    isscalar = False
    if dims is None or dims == 0 or set(dims) == {0}:
        dims = [1]
        isscalar = True
    type_ = type_.lower()
    tensor: Union[
        torch.CharTensor,
        torch.ShortTensor,
        torch.IntTensor,
        torch.LongTensor,
        torch.HalfTensor,
        torch.FloatTensor,
        torch.DoubleTensor,
    ]
    if type_ == "char":
        tensor = torch.CharTensor(*dims)
    elif type_ == "short":
        tensor = torch.ShortTensor(*dims)
    elif type_ == "int":
        tensor = torch.IntTensor(*dims)
    elif type_ == "long":
        tensor = torch.LongTensor(*dims)
    elif type_ == "half":
        tensor = torch.HalfTensor(*dims)
    elif type_ == "float":
        tensor = torch.FloatTensor(*dims)
    elif type_ == "double":
        tensor = torch.DoubleTensor(*dims)
    else:
        raise ValueError(
            "Unknown type, type should be one of the following strings: "
            "char, short, int, long, half, float, double"
        )
    tensor.fill_(value)  # type: ignore[call-overload]
    if isscalar:
        return g.op("Constant", *args, value_z=tensor, **kwargs)
    return g.op("Constant", *args, value_t=tensor, **kwargs)


# TODO(#76254): Remove the deprecated function.
@_deprecation.deprecated(
    "1.13",
    "1.14",
    "Internally use '_node_get' in symbolic_helper instead.",
)
def node_getitem(self, k):
    """Gets attributes of a node which is polymorphic over return type.

    This is monkey-patched onto Node.
    """
    sel = self.kindOf(k)
    return getattr(self, sel)(k)
