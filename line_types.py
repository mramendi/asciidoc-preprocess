from enum import Enum, auto
from typing import Dict, Any, List, Optional, Set
import copy


class StateType(Enum):
    """Main state types"""
    DELIMITED_BLOCK = auto()
    ROOT = auto()
    PARAGRAPH = auto()
    LIST_ITEM = auto()
    CONDITIONAL = auto()
    BLOCK_PREFIX = auto()
    SECTION_HEADER = auto()
    LINE_COMMENT = auto()
    ATTRIBUTE_DEFINITION = auto()


class StateSubtype(Enum):
    """State subtypes"""
    # For CONDITIONAL and DELIMITED_BLOCK
    START = auto()
    END = auto()

    # For CONDITIONAL only
    SINGLE_LINE = auto()

    # For DELIMITED_BLOCK only
    VERBATIM = auto()

    # For most types
    NORMAL = auto()

    # For PARAGRAPH and LIST_ITEM
    FIRST_LINE = auto()

    # For LIST_ITEM only
    JOINER = auto()  # a + line or a blank line in ancestor list continuation
    JOINED_FIRST_LINE = auto()
    JOINED_NORMAL = auto()
    TERMINATED = auto()
    JOINED_DELIMITED_BLOCK = auto()

    # For BLOCK_PREFIX only
    BLOCK_TITLE = auto()
    BLOCK_ATTRIBUTES = auto()



# Validation mapping: which subtypes are valid for which types
VALID_SUBTYPES: Dict[StateType, Set[StateSubtype]] = {
    StateType.DELIMITED_BLOCK: {
        StateSubtype.START, StateSubtype.END,
        StateSubtype.VERBATIM,
        StateSubtype.NORMAL
    },
    StateType.PARAGRAPH: {
        StateSubtype.NORMAL,
        StateSubtype.FIRST_LINE
    },
    StateType.LIST_ITEM: {
        StateSubtype.NORMAL,
        StateSubtype.FIRST_LINE,
        StateSubtype.JOINER, StateSubtype.JOINED_FIRST_LINE,
        StateSubtype.JOINED_NORMAL, StateSubtype.TERMINATED,
        StateSubtype.JOINED_DELIMITED_BLOCK
    },
    StateType.CONDITIONAL: {
        StateSubtype.START, StateSubtype.END, StateSubtype.SINGLE_LINE
    },
    StateType.ROOT: {
        StateSubtype.NORMAL
    },
    StateType.BLOCK_PREFIX: {
        StateSubtype.BLOCK_ATTRIBUTES,
        StateSubtype.BLOCK_TITLE
    },
    StateType.SECTION_HEADER: {
        StateSubtype.NORMAL
    },
    StateType.LINE_COMMENT: {
        StateSubtype.NORMAL
    },
    StateType.ATTRIBUTE_DEFINITION: {
        StateSubtype.NORMAL
    },
}


class State:
    """Represents a single state in the state stack"""

    def __init__(self, type: StateType, subtype: StateSubtype, parameters: Dict[str, Any] = None):
        # Validate type/subtype combination
        if subtype not in VALID_SUBTYPES[type]:
            valid = [s.name for s in VALID_SUBTYPES[type]]
            raise ValueError(
                f"Invalid subtype {subtype.name} for type {type.name}. "
                f"Valid subtypes: {', '.join(valid)}"
            )

        self.type = type
        self.subtype = subtype
        self.parameters = parameters if parameters is not None else {}

    def __repr__(self):
        return f"State({self.type.name}, {self.subtype.name}, {self.parameters})"

    def __eq__(self, other):
        if not isinstance(other, State):
            return False
        return (self.type == other.type and
                self.subtype == other.subtype and
                self.parameters == other.parameters)

    # Helper methods for common parameter access
    def get(self, key: str, default=None):
        """Get a parameter value"""
        return self.parameters.get(key, default)

    def __getitem__(self, key: str):
        """Access parameters with bracket notation"""
        return self.parameters[key]

    def __setitem__(self, key: str, value):
        """Set parameters with bracket notation"""
        self.parameters[key] = value

    # Helper method for creating an independent copy
    def duplicate(self) -> 'State':
        """Create an independent deep copy of this State"""
        return State(
            type=self.type,
            subtype=self.subtype,
            parameters=copy.deepcopy(self.parameters)
        )
        


class StateStack:
    """Stack of State objects representing the parsing context"""

    def __init__(self):
        self._stack: List[State] = []

    def top_by_type(self, type: StateType) -> Optional[State]:
        """Find the topmost state of the specified type"""
        for state in reversed(self._stack):
            if state.type == type:
                return state
        return None

    def top_by_type_and_subtype(self, type: StateType, subtype: StateSubtype) -> Optional[State]:
        """Find the topmost state matching both type and subtype"""
        for state in reversed(self._stack):
            if state.type == type and state.subtype == subtype:
                return state
        return None

    def top_delimiter(self) -> Optional[str]:
        """Find the top delimited block entry, return the delimiter"""
        delim_state = self.top_by_type(StateType.DELIMITED_BLOCK)
        if not delim_state:
            return None
        return delim_state.get('delimiter')

    def pop_until(self, state: State, inclusive: bool = True):
        """Pop and discard all items until the given state; if not `inclusive` keep that state"""
        if state not in self._stack:
            raise KeyError(f"State not in stack. \nstate: {state}\nstack: {self._stack}")
        popped = None
        while popped != state:
            popped = self._stack.pop()
        if not inclusive:
            self._stack.append(state)

    def pop_until_delimited_block(self, inclusive: bool = True) -> str:
        """Pop and discard all items until the top delimited block;
           if not `inclusive` keep that delimited block; return the delimiter"""
        delim_state = self.top_by_type(StateType.DELIMITED_BLOCK)
        if delim_state is None:
            raise KeyError(f"pop_until_delimited_block called but no delimited block found\nstack: {self._stack}")
        delimiter = delim_state.get('delimiter')
        self.pop_until(delim_state, inclusive)
        return delimiter

    def is_in_list_item(self) -> bool:
        """Check if currently in a list item"""
        return self.top_by_type(StateType.LIST_ITEM) is not None

    def is_in_verbatim_block(self) -> bool:
        """Check if currently in a verbatim delimited block"""
        for state in reversed(self._stack):
            if state.type == StateType.DELIMITED_BLOCK and state.subtype == StateSubtype.VERBATIM:
                return True
        return False

    def is_in_paragraph(self) -> bool:
        """Check if currently in a paragraph"""
        return self.top_by_type(StateType.PARAGRAPH) is not None

    def push(self, state: State):
        """Add a state to the top of the stack"""
        self._stack.append(state)

    def copy(self, other: 'StateStack'):
        """Copy another StateStack into this one (must be empty)"""
        if self._stack:
            raise ValueError("Attempted to copy into a non-empty state stack")
        self._stack = copy.deepcopy(other._stack)

    def duplicate(self) -> 'StateStack':
        """Return a deep copy of this StateStack as a new object"""
        new_stack = StateStack()
        new_stack._stack = copy.deepcopy(self._stack)
        return new_stack

    def until_delim_or_root(self):
        """Return a copy with all all items until root or a delimited block discarded; 
           the root/delimited block itself remains"""
        result = self.duplicate()
        while not result.top().type in [StateType.ROOT, StateType.DELIMITED_BLOCK]:
            result.pop()
        return result

    def top(self) -> State:
        """Get the top state without removing it"""
        if self._stack:
            return self._stack[-1]
        else:
            raise IndexError("top called on empty state stack")

    def pop(self) -> State:
        """Remove and return the top state"""
        if self._stack:
            return self._stack.pop()
        else:
            raise IndexError("pop called on empty state stack")

    def __len__(self):
        """Return the number of states in the stack"""
        return len(self._stack)

    def __repr__(self):
        return f"StateStack({self._stack})"
    
    def __eq__(self, other):
        if not isinstance(other, StateStack):
              return False
        return self._stack == other._stack

    def pretty(self, indent: int = 0) -> str:
        """Return a pretty-printed representation of the state stack (top to bottom)"""
        if not self._stack:
            return " " * indent + "(empty stack)"

        lines = []
        # Display from top to bottom (reversed list order)
        for i in range(len(self._stack) - 1, -1, -1):
            state = self._stack[i]
            prefix = " " * indent + f"[{i}] "
            state_str = f"{state.type.name}/{state.subtype.name}"
            if state.parameters:
                state_str += f" {state.parameters}"
            lines.append(prefix + state_str)
        return "\n".join(lines)
    






class Line:
    """The main class abstracting an entire line"""

    def __init__(self, id: int, content: str):
        self._id = id  # the immutable line ID; all other values are mutable
        self.content = content  # the text in the line
        self.state_stack = StateStack()
        self.state_stack_after = StateStack()

    @property
    def id(self) -> int:
        """Immutable line identifier"""
        return self._id

    def pretty(self) -> str:
        """Return a pretty-printed representation of this line"""
        result = []
        result.append(f"\nLine {self.id}: {repr(self.content)}")
        result.append("  State stack:")
        result.append(self.state_stack.pretty(indent=4))
        if len(self.state_stack_after) > 0:
            result.append("  State stack after:")
            result.append(self.state_stack_after.pretty(indent=4))
        return "\n".join(result)

    def prepend(self, prefix: str):
        """Prepend text to the line content"""
        self.content = prefix + self.content

    def append(self, suffix: str):
        """Append text to the line content"""
        self.content += suffix
