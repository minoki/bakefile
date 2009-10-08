#
#  This file is part of Bakefile (http://www.bakefile.org)
#
#  Copyright (C) 2009 Vaclav Slavik
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to
#  deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
#  sell copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
#  IN THE SOFTWARE.
#

import types
import expr

# Metaclass used for all extensions in order to implement automatic
# extensions registration. For internal use only.
class _ExtensionMetaclass(type):

    def __init__(cls, name, bases, dct):
        super(_ExtensionMetaclass, cls).__init__(name, bases, dct)

        assert len(bases) == 1, "multiple inheritance not supported"

        # skip base classes, only register implementations:
        if name == "Extension":
            return
        if cls.__base__ is Extension:
            # initialize list of implementations for direct extensions:
            cls._implementations = {}
            return

        if cls.name is None:
            # This must be a helper class derived from a particular extension,
            # but not a fully implemented extension; see e.g. MakefileToolset
            # base class for MingwToolset, BorlandToolset etc.
            return

        # for "normal" implementations of extensions, find the extension
        # type class (we need to handle the case of deriving from an existing
        # extension):
        base = cls.__base__
        while not base.__base__ is Extension:
            base = base.__base__
        if cls.name in base._implementations:
            existing = base._implementations[cls.name]
            raise RuntimeError("conflicting implementations for %s \"%s\": %s.%s and %s.%s" %
                               (base.__name__,
                                cls.name,
                                cls.__module__, cls.__name__,
                                existing.__module__, existing.__name__))
        base._implementations[cls.name] = cls



# instances of all already requested extensions, keyed by (type,name)
_extension_instances = {}


class Extension(object):
    """
    Base class for all Bakefile extensions.

    Extensions are singletons, there's always only one instance of given
    extension at runtime. Use the get() method called on appropriate extension
    type to obtain it. For example:

        exe = TargetType.get("exe")
        # ...do something with it...

    .. attribute:: name

       Use-visible name of the extension. For example, the name for targets
       extensions is what is used in target declarations; likewise for
       property names.
    """

    __metaclass__ = _ExtensionMetaclass

    @classmethod
    def get(cls, name=None):
        """
        This class method is used to get an instance of an extension. In can
        be used in one of two ways:

        1. When called on an extension type class with *name* argument, it
           returns instance of extension with given name and of the extension
           type on which this classmethod was called:

           >>> bkl.api.Toolset.get("gnu")
               <bkl.plugins.gnu.GnuToolset object at 0x2232950>

        2. When called without the *name* argument, it must be called on
           particular extension class and returns its (singleton) instance:

           >>> GnuToolset.get()
               <bkl.plugins.gnu.GnuToolset object at 0x2232950>

        :param name: Name of the extension to read; this corresponds to
            class' "name" attribute. If not specified, then get() must be
            called on a extension, not extension base class.
        """
        if name is None:
            assert cls.name is not None, \
                   "get() can only be called on fully implemented extension"
            name = cls.name
            # find the extension base class:
            while not cls.__base__ is Extension:
                cls = cls.__base__
        else:
            assert cls.name is None, \
                   "get(name) can only be called on extension base class"

        global _extension_instances
        key = (cls, name)
        if key not in _extension_instances:
            _extension_instances[key] = cls._implementations[name]()
        return _extension_instances[key]


    @classmethod
    def all(cls):
        """
        Returns iterator over instances of all implementations of this extension
        type.
        """
        for name in cls.all_names():
            yield cls.get(name)


    @classmethod
    def all_names(cls):
        """
        Returns names of all implementations of this extension type.
        """
        return cls._implementations.keys()


    name = None
    _implementations = {}



class Property(object):
    """
    Properties describe variables on targets etc. that are part of the API --
    that is, they have special meaning for the toolset and.
    Unlike free-form variables, properties have a type associated with them
    and any values assigned to them are checked for type correctness. They
    can optionally have a default value, too.

    .. attribute:: name

       Name of the property/variable.

    .. attribute:: type

       Type of the property, as :class:`bkl.vartypes.Type` instance.

    .. attribute:: default

       Default value of the property (as :class:`bkl.expr.Expr`)
       or :const:`None`.

    .. attribute:: readonly

       Indicates if the property is read-only. Read-only properties can only
       have the default value and cannot be modified. They are typically
       derived from some other value and exist as a convenience. An example
       of read-only property is the ``id`` property on targets.

    .. attribute:: doc

       Optional documentation for the property.

    Example usage:

    .. code-block:: python

       class FooTarget(bkl.api.TargetType):
           name = "foo"
           properties = [
               Property("defines", default="",
                        doc="compiler predefined symbols for the foo compiler")
           ]
           ...

    """

    def __init__(self, name, type, default=None, readonly=False, doc=None):
        self.name = name
        self.type = type
        self.default = default
        self.readonly = readonly
        self.__doc__ = doc


    def default_expr(self, for_obj):
        """
        Returns the value of :attr:`default` expression. Always returns
        an :class:`bkl.expr.Expr` instance, even if the default is
        :const:`None`.

        :param for_obj: The class:`bkl.model.ModelPart` object to return
            the default for. If the default value is defined, its expression
            is evaluated in the context of *for_obj*.
        """
        if self.default is None:
            return expr.NullExpr()
        elif (type(self.default) is types.FunctionType or
              type(self.default) is types.MethodType):
            # default is defined as a callback function
            return self.default(for_obj)
        else:
            # FIXME: if 'default' is a string, parse it into an expression
            #        (in context of `for_obj`!)
            return self.default



class BuildNode(object):
    """
    BuildNode represents a single node in traditional make-style build graph.
    Bakefile's model is higher-level than that, its targets may represent
    entities that will be mapped into several makefile targets. But BuildNode
    is the simplest element of build process: a list of commands to run
    together with dependencies that describe when to run it and a list of
    outputs the commands create.

    Node's commands are executed if either a) some of its outputs doesn't
    exist or b) any of the inputs was modified since the last time the outputs
    were modified.

    .. seealso:: :meth:`bkl.api.TargetType.get_build_subgraph`

    .. attribute:: name

       Name of build node. May be empty. If not empty and the node has no
       output files (i.e. is *phony*), then this name is used in the generated
       makefiles. It is ignored in all other cases.

    .. attribute:: inputs

       List of all inputs for this node. Its items are filenames (as
       :class:`bkl.expr.PathExpr` expressions) or (phony) target names.

    .. attribute:: outputs

       List of all outputs this node generates. Its items are filenames (as
       :class:`bkl.expr.PathExpr` expressions).

       A node with no outputs is called *phony*.

    .. attribute:: commands:

       List of commands to execute when the rebuild condition is met, as
       :class:`bkl.expr.Expr`.
    """
    def __init__(self, commands, inputs=[], outputs=[], name=None):
        self.commands = commands
        self.inputs = inputs
        self.outputs = outputs
        self.name = name
        assert name or outputs, \
               "phony target must have a name, non-phony must have outputs"



class FileType(Extension):
    """
    Description of a file type. File types are used by
    :class:`bkl.api.FileCompiler` to define both input and output files.

    .. attribute:: extensions

       List of extensions for this file type, e.g. ``["cpp", "cxx", "C"]``.
    """

    def __init__(self, extensions=[]):
        self.extensions = extensions


    def detect(self, filename):
        """
        Returns True if the file is of this file type. This method is only
        called if the file has one of the extensions listed in
        :attr:`extensions`. By default, returns True.

        :param filename: Name of the file to check. Note that this is native
                         filename and points to existing file.
        """
        return True



class FileCompiler(Extension):
    """
    In Bakefile API, FileCompiler is used to define all compilation steps.

    Traditionally, the term *compiler* is used for a tool that compiles source
    code into object files. In Bakefile, a *file compiler* is generalization of
    this term: it's a tool that compiles file or files of one object type into
    one or more files of another type. In this meaning, a C/C++ compiler is a
    *file compiler*, but so is a linker (it "compiles" object files into
    executables) or e.g. Lex/Yacc compiler or Qt's MOC preprocessor.
    """

    #: :class:`bkl.api.FileType` for compiler's input file.
    in_type = None

    #: :class:`bkl.api.FileType` for compiler's output file.
    out_type = None

    ONE_TO_ONE  = "1"
    MANY_TO_ONE = "many"

    #: Cardinality of the compiler. That is, whether it compiles one file into
    #: one file (:const:`FileCompiler.ONE_TO_ONE`, e.g. C compilers) or whether
    #: it compiles many files of the same type into one output file
    #: (:const:`FileCompiler.MANY_TO_ONE`, e.g. the linker or Java compiler).
    cardinality = ONE_TO_ONE



class TargetType(Extension):
    """
    Base class for implementation of a new target type.
    """

    #: List of all properties supported on this target type,
    #: as :class:`Property` instances. Note that properties list is
    #: automagically inherited from base classes, if any.
    properties = [] # will be initialized to stdprops.STD_TARGET_PROPS

    def get_build_subgraph(self, target):
        """
        Returns list of :class:`bkl.api.BuildNode` objects with description
        of this target's local part of build graph -- that is, its part needed
        to produce output files associated with this target.

        Usually, exactly one BuildNode will be returned, but it's possible to
        have TargetTypes that correspond to more than one makefile target
        (e.g. libtool-style libraries or gettext catalogs).
        """
        raise NotImplementedError



class Toolset(Extension):
    """
    This class encapsulates generating of the project files or makefiles.

    The term "toolset" refers to collection of tools (compiler, linker, make,
    IDE, ...) used to compile programs. For example, "Visual C++ 2008",
    "Visual C++ 2005", "Xcode" or "Borland C++" are toolsets.

    In Bakefile API, this class is responsible for creation of the output. It
    puts all the components (platform-specific commands, make syntax, compiler
    invocation, ...) together and writes out the makefiles or projects.
    """

    #: List of all properties supported on this target type,
    #: as :class:`Property` instances. Note that properties list is
    #: automagically inherited from base classes, if any.
    properties = []


    def generate(self, project):
        """
        Generates all output files for this toolset.

        :param project: model.Project instance with complete description of the
            output. It was already preprocessed to remove content not relevant
            for this toolset (e.g. targets or sub-modules built conditionally
            only for other toolsets, conditionals that are always true or false
            within the toolset and so on).
        """
        raise NotImplementedError
