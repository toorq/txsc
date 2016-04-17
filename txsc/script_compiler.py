from collections import OrderedDict
import ast
import sys
from pkg_resources import iter_entry_points

from ply import yacc

from txsc.optimize import Optimizer
from txsc.txscript import TxScriptLanguage
from txsc.asm import ASMLanguage
from txsc.btcscript import BtcScriptLanguage

# Load known languages in case we're running locally.
languages = [ASMLanguage, BtcScriptLanguage, TxScriptLanguage]
for entry_point in iter_entry_points(group='txsc.language'):
    lang_maker = entry_point.load()
    lang = lang_maker()
    if lang.name not in [i.name for i in languages]:
        languages.append(lang)

class Verbosity(object):
    """Options that depend on verbosity."""
    max_verbosity = 3
    def __init__(self, value):
        self.value = value
        self.quiet = value == 0     # Only output the compiled source.
        self.show_linear_ir = value > 0 # Show the linear intermediate representation.
        self.echo_input = value > 2 # Echo the source that was input.

class ScriptCompiler(object):
    """Script compiler."""
    def __init__(self):
        self.outputs = OrderedDict()
        self.optimize = True
        self.setup_languages()

    def setup_languages(self):
        self.langs = list(languages)
        self.input_languages = {i.name: i for i in filter(lambda cls: cls.has_source_visitor(), self.langs)}
        self.output_languages = {i.name: i for i in filter(lambda cls: cls.has_target_visitor(), self.langs)}

    def setup_options(self, options):
        self.options = options
        self.verbosity = Verbosity(self.options.verbosity)
        self.optimize = not self.options.no_optimize

        # Compilation source and target.
        self.source_lang = self.input_languages[self.options.source_lang]
        self.target_lang = self.output_languages[self.options.target_lang]

        self.output_file = self.options.output_file

    def compile(self, source_lines):
        self.outputs.clear()

        if self.verbosity.echo_input:
            self.outputs['Input'] = source_lines

        try:
            instructions = self.source_lang().process_source(source_lines)
        except SyntaxError as e:
            print('Error encountered during compilation of source:')
            print(e)
            sys.exit(1)

        if self.verbosity.show_linear_ir:
            self.outputs['Linear Intermediate Representation'] = str(instructions)

        self.process_linear_ir(instructions)

    def process_linear_ir(self, instructions):
        """Process linear intermediate representation."""
        # Perform optimizations.
        if self.optimize:
            optimizer = Optimizer()
            optimizer.optimize(instructions)
            self.outputs['Optimized Linear Representation'] = str(instructions)

        self.process_targets(instructions)

    def process_targets(self, instructions):
        """Process compilation targets."""
        self.outputs[self.target_lang.name] = self.target_lang().compile_instructions(instructions)

        self.output()

    def output(self):
        """Output results."""
        formats = OrderedDict(self.outputs)
        # Hide optimized linear representation if no optimizations were performed.
        if formats.get('Optimized Linear Representation') and formats.get('Linear Intermediate Representation'):
            if formats['Linear Intermediate Representation'] == formats['Optimized Linear Representation']:
                del formats['Optimized Linear Representation']

        s = ['%s:\n  %s\n' % (k, v) for k, v in formats.items()]
        s = '\n'.join(s)
        if s.endswith('\n'):
            s = s[:-1]
        if self.verbosity.quiet:
            s = self.outputs[self.target_lang.name]

        if self.output_file:
            with open(self.output_file, 'w') as f:
                f.write(s)
        else:
            print(s)
