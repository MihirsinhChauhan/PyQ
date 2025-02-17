from __future__ import annotations

import torch
from numpy.typing import ArrayLike
from torch.nn import Module

from pyqtorch.core.batched_operation import (
    _apply_batch_gate,
    create_controlled_batch_from_operation,
)
from pyqtorch.core.utils import OPERATIONS_DICT


class RotationGate(Module):
    n_params = 1

    def __init__(self, gate: str, qubits: ArrayLike, n_qubits: int):
        """
        Represents a rotation gate in a quantum circuit.

        Args:
            gate (str): The name of the gate.
            qubits (ArrayLike): The target qubits for the gate.
            n_qubits (int): The total number of qubits in the circuit.

        Attributes:
            imat (torch.Tensor): The identity matrix.
            paulimat (torch.Tensor): The matrix representation of the gate.

        Examples:
            ```python exec="on" source="above" result="json"
            from pyqtorch.modules.primitive import RotationGate

            qubits = [0, 1]
            n_qubits = 2
            gate = RotationGate("X", qubits, n_qubits)
            ```
        """
        super().__init__()
        self.qubits = qubits
        self.n_qubits = n_qubits
        self.gate = gate
        self.register_buffer("imat", OPERATIONS_DICT["I"])
        self.register_buffer("paulimat", OPERATIONS_DICT[gate])

    def matrices(self, thetas: torch.Tensor) -> torch.Tensor:
        """
        Generate the rotation matrices based on the input angles.

        Args:
            thetas (torch.Tensor): The rotation angles.

        Returns:
            torch.Tensor: The rotation matrices.

        Examples:
            ```python exec="on" source="above" result="json"
            thetas = torch.tensor([0.5])
            matrices = gate.matrices(thetas)
            ```
        """
        theta = thetas.squeeze(0) if thetas.ndim == 2 else thetas
        batch_size = len(theta)
        return rot_matrices(theta, self.paulimat, self.imat, batch_size)

    def apply(self, matrices: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        """
        Apply the rotation matrices to the input state.

        Args:
            matrices (torch.Tensor): The rotation matrices.
            state (torch.Tensor): The input state.

        Returns:
            torch.Tensor: The resulting state after applying the rotation gates.

        Examples:
            ```python exec="on" source="above" result="json"
            matrices = torch.tensor(...)  # Rotation matrices
            state = torch.tensor(...)  # Input state
            new_state = gate.apply(matrices, state)
            ```
        """
        batch_size = matrices.size(-1)
        return _apply_batch_gate(state, matrices, self.qubits, self.n_qubits, batch_size)

    def forward(self, state: torch.Tensor, thetas: torch.Tensor) -> torch.Tensor:
        """
        Apply the rotation gate to the input state.

        Args:
            state (torch.Tensor): The input state.
            thetas (torch.Tensor): The rotation angles.

        Returns:
            torch.Tensor: The resulting state after applying the rotation gate.

        Examples:
            ```python exec="on" source="above" result="json"
            state = torch.tensor(...)  # Input state
            thetas = torch.tensor(...)  # Rotation angles
            new_state = gate.forward(state, thetas)
            ```
        """
        mats = self.matrices(thetas)
        return self.apply(mats, state)

    def extra_repr(self) -> str:
        return f"qubits={self.qubits}, n_qubits={self.n_qubits}"


def rot_matrices(
    theta: torch.Tensor, P: torch.Tensor, I: torch.Tensor, batch_size: int  # noqa: E741
) -> torch.Tensor:
    """
       Generate a batch of rotation matrices.

       Args:
           theta (torch.Tensor): The rotation angles.
           P (torch.Tensor): The matrix representation of the gate.
           I (torch.Tensor): The identity matrix.
           batch_size (int): The size of the batch.

       Returns:
           torch.Tensor: A batch of rotation gates after applying theta.

       Examples:
           ```python exec="on" source="above" result="json"
           theta = torch.tensor([0.5])
           P = torch.tensor(...)  # Matrix representation of the gate
           I = torch.tensor(...)  # Identity matrix
           batch_size = 10
           matrices = rot_matrices(theta, P, I, batch_size)
           ```
       """
    cos_t = torch.cos(theta / 2).unsqueeze(0).unsqueeze(1)
    cos_t = cos_t.repeat((2, 2, 1))
    sin_t = torch.sin(theta / 2).unsqueeze(0).unsqueeze(1)
    sin_t = sin_t.repeat((2, 2, 1))

    batch_imat = I.unsqueeze(2).repeat(1, 1, batch_size)
    batch_operation_mat = P.unsqueeze(2).repeat(1, 1, batch_size)

    return cos_t * batch_imat - 1j * sin_t * batch_operation_mat


class U(Module):

    n_params = 3

    def __init__(self, qubits: ArrayLike, n_qubits: int):
        """
               Represents a parametrized arbitrary rotation along the axes of the Bloch sphere.
               The angles `phi, theta, omega` in tensor format, applied as:
                   U(phi, theta, omega) = RZ(omega)RY(theta)RZ(phi)
               Arguments:
                   qubits (ArrayLike): The target qubits for the U gate. It should be a list of qubits.
                   n_qubits (int): The total number of qubits in the circuit.
               """
        super().__init__()
        self.qubits = qubits
        self.n_qubits = n_qubits

        self.register_buffer("a", torch.tensor([[1, 0], [0, 0]], dtype=torch.cdouble).unsqueeze(2))
        self.register_buffer("b", torch.tensor([[0, 1], [0, 0]], dtype=torch.cdouble).unsqueeze(2))
        self.register_buffer("c", torch.tensor([[0, 0], [1, 0]], dtype=torch.cdouble).unsqueeze(2))
        self.register_buffer("d", torch.tensor([[0, 0], [0, 1]], dtype=torch.cdouble).unsqueeze(2))

    def matrices(self, thetas: torch.Tensor) -> torch.Tensor:
        """
                Generate a batch of U gate matrices.

                Args:
                    thetas (torch.Tensor): The rotation angles as a tensor of size (3, batch_size).

                Returns:
                    torch.Tensor: A batch of U gate matrices.

                Raises:
                    AssertionError: If thetas has an invalid shape.

                Examples:
                    ```python exec="on" source="above" result="json"
                    thetas = torch.tensor([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
                    u_gate = U(qubits, n_qubits)
                    matrices = u_gate.matrices(thetas)
                    ```
                """
        if thetas.ndim == 1:
            thetas = thetas.unsqueeze(1)
        assert thetas.size(0) == 3
        phi, theta, omega = thetas[0, :], thetas[1, :], thetas[2, :]
        batch_size = thetas.size(1)

        t_plus = torch.exp(-1j * (phi + omega) / 2)
        t_minus = torch.exp(-1j * (phi - omega) / 2)
        sin_t = torch.sin(theta / 2).unsqueeze(0).unsqueeze(1).repeat((2, 2, 1))
        cos_t = torch.cos(theta / 2).unsqueeze(0).unsqueeze(1).repeat((2, 2, 1))

        a = self.a.repeat(1, 1, batch_size) * cos_t * t_plus
        b = self.b.repeat(1, 1, batch_size) * sin_t * torch.conj(t_minus)
        c = self.c.repeat(1, 1, batch_size) * sin_t * t_minus
        d = self.d.repeat(1, 1, batch_size) * cos_t * torch.conj(t_plus)
        return a - b + c + d

    def apply(self, matrices: torch.Tensor, state: torch.Tensor) -> torch.Tensor:

        batch_size = matrices.size(-1)
        return _apply_batch_gate(state, matrices, self.qubits, self.n_qubits, batch_size)

    def forward(self, state: torch.Tensor, thetas: torch.Tensor) -> torch.Tensor:
        """
                Represents batched state and theta forwarding  to the matrices
                and apply functions that are part of the U gate implementation
                Arguments:
                    state  (torch.Tensor): batched state
                    thetas (torch.Tensor): Tensor of size (3, batch_size) which
                    contains the values of `phi`/`theta`/`omega`
                Returns:
                    torch.Tensor: the resulting state after applying the gate
            """
        mats = self.matrices(thetas)
        return self.apply(mats, state)

    def extra_repr(self) -> str:
        return f"qubits={self.qubits}, n_qubits={self.n_qubits}"


class ControlledRotationGate(Module):
    n_params = 1

    def __init__(self, gate: str, qubits: ArrayLike, n_qubits: int):
        super().__init__()
        self.qubits = qubits
        self.n_qubits = n_qubits
        self.gate = gate
        self.register_buffer("imat", OPERATIONS_DICT["I"])
        self.register_buffer("paulimat", OPERATIONS_DICT[gate])

    def matrices(self, thetas: torch.Tensor) -> torch.Tensor:
        theta = thetas.squeeze(0) if thetas.ndim == 2 else thetas
        batch_size = len(theta)
        return rot_matrices(theta, self.paulimat, self.imat, batch_size)

    def apply(self, matrices: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        batch_size = matrices.size(-1)
        controlled_mats = create_controlled_batch_from_operation(matrices, batch_size)
        return _apply_batch_gate(state, controlled_mats, self.qubits, self.n_qubits, batch_size)

    def forward(self, state: torch.Tensor, thetas: torch.Tensor) -> torch.Tensor:
        mats = self.matrices(thetas)
        return self.apply(mats, state)

    def extra_repr(self) -> str:
        return f"qubits={self.qubits}, n_qubits={self.n_qubits}"


class RX(RotationGate):
    def __init__(self, qubits: ArrayLike, n_qubits: int):
        """
                Represents an X-axis rotation (RX) gate in a quantum circuit.
                The RX gate class creates a single-qubit RX gate that performs
                a given rotation around the X axis.
                Arguments:
                    qubits (ArrayLike): The qubits to apply the RX gate to.
                    It should be a list of qubit indices.
                    n_qubits (int): The total number of qubits in the circuit.
                Examples:
                ```python exec="on" source="above" result="json"
                import torch
                import pyqtorch.modules as pyq
                # Create an RX gate
                rx_gate = pyq.RX(qubits=[0], n_qubits=1)
                # Create a zero state
                z_state = pyq.zero_state(n_qubits=1)
                #Create a random theta angle
                theta = torch.rand(1)
                # Every rotational gate accepts a second parameter that is expected to be a Theta angle.
                # Apply the RX gate to the zero state with your random theta as a second parameter.
                result=rx_gate(z_state, theta)
                print(result)
                ```
                """
        super().__init__("X", qubits, n_qubits)


class RY(RotationGate):
    def __init__(self, qubits: ArrayLike, n_qubits: int):
        """
               Represents a Y-axis rotation (RY) gate in a quantum circuit.
               The RY gate class creates a single-qubit RY gate that performs
               a given rotation around the Y axis.
               Arguments:
                   qubit (ArrayLike): The qubit index to apply the RY gate to.
                   n_qubits (int): The total number of qubits in the circuit.
               Examples:
               ```python exec="on" source="above" result="json"
               import torch
               import pyqtorch.modules as pyq
               # Create an RY gate
               ry_gate = pyq.RY(qubits=[0], n_qubits=1)
               # Create a zero state
               z_state = pyq.zero_state(n_qubits=1)
               # Create a random theta angle
               theta = torch.rand(1)
               # Apply the RY gate to the zero state with the random theta angle
               result = ry_gate(z_state, theta)
               print(result)
               ```
               """
        super().__init__("Y", qubits, n_qubits)


class RZ(RotationGate):
    def __init__(self, qubits: ArrayLike, n_qubits: int):
        """
               Represents a Z-axis rotation (RZ) gate in a quantum circuit.
               The RZ gate class creates a single-qubit RZ gate that performs
               a given rotation around the Z axis.
               Arguments:
                   qubits (ArrayLike): The qubit index or list of qubit indices to apply the RZ gate to.
                   n_qubits (int): The total number of qubits in the circuit.
               Examples:
               ```python exec="on" source="above" result="json"
               import torch
               import pyqtorch.modules as pyq
               # Create an RZ gate
               rz_gate = pyq.RZ(qubits=[0], n_qubits=1)
               # Create a zero state
               z_state = pyq.zero_state(n_qubits=1)
               # Create a random theta angle
               theta = torch.rand(1)
               # Apply the RZ gate to the zero state with the random theta angle
               result = rz_gate(z_state, theta)
               print(result)
               ```
               """
        super().__init__("Z", qubits, n_qubits)


class CRX(ControlledRotationGate):
    def __init__(self, qubits: ArrayLike, n_qubits: int):
        """
                Represents a controlled-X-axis rotation (CRX) gate in a quantum circuit.
                The CRX gate class creates a controlled RX gate, applying the RX according
                to the control qubit state.
                Arguments:
                    qubits (ArrayLike): The qubit index or list of qubit indices where
                    the controlled CRX gate acts on.
                    n_qubits (int): The total number of qubits in the circuit.
                Examples:
                    ```python exec="on" source="above" result="json"
                # Create a CRX gate
                #The CRX gate is a controlled version of the RX gate.
                #It applies an RX rotation to the target qubit based on the state of the control qubit.
                #The gate takes two qubits as input: the control qubit and the target qubit.
                crx_gate = pyq.CRX(qubits=[0, 1], n_qubits=2)
                # Create a X gate
                x_gate=pyq.X(qubits=[0], n_qubits=2)
                # Create a zero state
                z_state = pyq.zero_state(n_qubits=2)
                #Apply an X gate to zero state to change its  state from 0 to 1
                activation_state=x_gate(z_state)
                # Create a random theta angle
                theta = torch.rand(1)
                # Apply the CRX gate to the activation state with the random theta angle
                result = crx_gate(activation_state, theta)
                print(result)
                    ```
                """
        super().__init__("X", qubits, n_qubits)


class CRY(ControlledRotationGate):
    def __init__(self, qubits: ArrayLike, n_qubits: int):
        """
                Represents a controlled-Y-axis rotation (CRY) gate in a quantum circuit.
                The CRY gate class creates a controlled RY gate, applying the RY according
                to the control qubit state.
                Arguments:
                    qubits (ArrayLike): The qubit index or list of qubit indices where
                    the controlled CRY gate acts on.
                    n_qubits (int): The total number of qubits in the circuit.
                Examples:
                    ```python exec="on" source="above" result="json"
                import torch
                import pyqtorch.modules as pyq
                # Create a CRY gate
                # The CRY gate is a controlled version of the RY gate.
                # It applies an RY rotation to the target qubit based on the state of the control qubit.
                # The gate takes two qubits as input: the control qubit and the target qubit.
                cry_gate = pyq.CRY(qubits=[0, 1], n_qubits=2)
                # Create a Y gate
                y_gate = pyq.Y(qubits=[0], n_qubits=2)
                # Create a zero state
                z_state = pyq.zero_state(n_qubits=2)
                # Apply a Y gate to the zero state to change its state
                activation_state = y_gate(z_state)
                # Create a random theta angle
                theta = torch.rand(1)
                # Apply the CRY gate to the activation state with the random theta angle
                result = cry_gate(activation_state, theta)
                print(result)
                    ```
                """
        super().__init__("Y", qubits, n_qubits)


class CRZ(ControlledRotationGate):
    def __init__(self, qubits: ArrayLike, n_qubits: int):
        """
                Represents a controlled-Z-axis rotation (CRZ) gate in a quantum circuit.
                The CRZ gate class creates a controlled RZ gate, applying the RZ according
                to the control qubit state.
                Arguments:
                    qubits (ArrayLike): The qubit index or list of qubit indices where
                    the controlled CRZ gate acts on.
                    n_qubits (int): The total number of qubits in the circuit.
                Examples:
                    ```python exec="on" source="above" result="json"
                    import torch
                    import pyqtorch.modules as pyq
                    # Create a CRZ gate
                    # The CRZ gate is a controlled version of the RZ gate.
                    # It applies an RZ rotation to the target qubit based on the state of the control qubit.
                    # The gate takes two qubits as input: the control qubit and the target qubit.
                    crz_gate = pyq.CRZ(qubits=[0, 1], n_qubits=2)
                    # Create a X gate
                    x_gate = pyq.X(qubits=[0], n_qubits=2)
                    # Create a zero state
                    z_state = pyq.zero_state(n_qubits=2)
                    # Apply a X gate to the zero state to change its state
                    activation_state = x_gate(z_state)
                    # Create a random theta angle
                    theta = torch.rand(1)
                    # Apply the CRZ gate to the activation state with the random theta angle
                    result = crz_gate(activation_state, theta)
                    print(result)
                    ```
                """
        super().__init__("Z", qubits, n_qubits)


class CPHASE(Module):
    n_params = 1

    def __init__(self, qubits: ArrayLike, n_qubits: int):
        """
                Represents a controlled-phase (CPHASE) gate in a quantum circuit.
                The CPhase gate class creates a controlled Phase gate, applying the PhaseGate
                according to the control qubit state.
                Arguments:
                    qubits (ArrayLike): The control and target qubits for the CPHASE gate.
                    It should be a list of two qubits.
                    n_qubits (int): The total number of qubits in the circuit.
                """
        super().__init__()
        self.qubits = qubits
        self.n_qubits = n_qubits
        self.register_buffer("imat", torch.eye(4, dtype=torch.cdouble))

    def matrices(self, thetas: torch.Tensor) -> torch.Tensor:
        # NOTE: thetas are assumed to be of shape (1,batch_size) or (batch_size,) because we
        # want to allow e.g. (3,batch_size) in the U gate.
        theta = thetas.squeeze(0) if thetas.ndim == 2 else thetas
        batch_size = len(theta)
        mat = self.imat.repeat((batch_size, 1, 1))
        mat = torch.permute(mat, (1, 2, 0))
        phase_rotation_angles = torch.exp(torch.tensor(1j) * theta).unsqueeze(0).unsqueeze(1)
        mat[3, 3, :] = phase_rotation_angles
        return mat

    def apply(self, matrices: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        batch_size = matrices.size(-1)
        return _apply_batch_gate(state, matrices, self.qubits, self.n_qubits, batch_size)

    def forward(self, state: torch.Tensor, thetas: torch.Tensor) -> torch.Tensor:
        mats = self.matrices(thetas)
        return self.apply(mats, state)

    def extra_repr(self) -> str:
        return f"qubits={self.qubits}, n_qubits={self.n_qubits}"
