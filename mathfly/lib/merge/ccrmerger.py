'''
Created on Sep 12, 2015

@author: synkarius
Standard merge filter: app_merge'''
from collections import OrderedDict
from itertools import izip_longest
from dragonfly.grammar.elements import RuleRef, Alternative, Repetition
from dragonfly.grammar.grammar_base import Grammar
from dragonfly.grammar.rule_compound import CompoundRule

from mathfly.lib import utilities
from mathfly.lib.merge.mergepair import MergePair, MergeInf
from mathfly.lib.merge.mergerule import MergeRule
import os

BASE_PATH = os.path.realpath(__file__).split("\\lib\\")[0].replace("\\", "/")

SETTINGS = utilities.load_toml_file(BASE_PATH + "/config/settings.toml")
CCR_PATH = BASE_PATH + "/" + SETTINGS["ccr_path"]

def app_merge(mp):
    '''forces app rules to define which parts of the base rule they will accept'''
    if mp.type == MergeInf.APP:
        base = mp.rule1  #base copy, actually
        if base is None:
            return
        app = mp.rule2
        mw = app.get_merge_with()
        specs_per_rulename = mp.extras
        '''flatten acceptable specs into a list'''
        acceptable_specs = []
        for rulename in specs_per_rulename:
            if rulename in mw:
                acceptable_specs.extend(specs_per_rulename[rulename])
        '''remove anything the app rule hasn't defined as mergeable'''
        for spec in base.mapping_actual().keys():
            if not spec in acceptable_specs:
                del base.mapping_actual()[spec]


class CCRMerger(object):
    CORE = []
    _GLOBAL = "global"
    _APP = "app"
    _SELFMOD = "selfmod"
    _ORDER = "enabling_order"

    def __init__(self, use_real_config=True):
        self._grammars = [
        ]  # cannot put multiple large rules in a single grammar despite context separation
        # original copies of rules
        self._global_rules = {}
        self._app_rules = {}
        # self modifying rules (don't make copies)
        self._self_modifying_rules = {}
        # filter functions
        self._filters = []
        # active rules
        self._base_global = None
        self._global_with_apps = []
        # config
        self.use_real_config = use_real_config
        self.load_config()
        self.add_filter(app_merge)

    '''config file stuff'''

    def save_config(self):
        if self.use_real_config:
            utilities.save_toml_file(self._config, CCR_PATH)

    def load_config(self):
        if self.use_real_config:
            self._config = utilities.load_toml_file(CCR_PATH)
        else:
            self._config = {}

    def update_config(self):
        '''call this after all rules have been added'''
        # Rebuild ccr.toml, rules which have not been registered will be removed,
        # new rules will be added
        new_config = {}
        for tag, rules in {CCRMerger._GLOBAL: self.global_rule_names(),
                    CCRMerger._APP: self.app_rule_names(),
                    CCRMerger._SELFMOD: self.selfmod_rule_names()}.iteritems():
            new_config[tag] = {}
            if not tag in self._config:
                self._config[tag] = {}
            for name in rules:
                if name in self._config[tag]:
                    new_config[tag][name] = self._config[tag][name]
                else:
                    new_config[tag][name] = False

        self._config = new_config
        self.save_config()


    '''setup: adding rules and filters'''
    def add_global_rule(self, rule):
        assert rule.get_context(
        ) is None, "global rules may not have contexts, " + rule.get_pronunciation(
        ) + " has a context: " + str(rule.get_context())
        assert isinstance(rule, MergeRule) and not hasattr(rule, "set_merger"), \
            "only MergeRules may be added as global rules; use add_selfmodrule() or add_app_rule()"
        self._add_to(rule, self._global_rules)

    def add_app_rule(self, rule, context=None):
        if context is not None and rule.get_context() is None: rule.set_context(context)
        assert rule.get_context(
        ) is not None, "app rules must have contexts, " + rule.get_pronunciation(
        ) + " has no context"
        assert rule.get_merge_with(
        ) is not None, "app rules must define mwith, " + rule.get_pronunciation(
        ) + " has no mwith"
        self._add_to(rule, self._app_rules)

    def add_selfmodrule(self, rule):
        assert hasattr(
            rule,
            "set_merger"), "only SelfModifyingRules may be added by add_selfmodrule()"
        assert not hasattr(rule,
                           "master_node"), "NodeRules are not permitted in the merger"
        rule.set_merger(self)
        self._add_to(rule, self._self_modifying_rules)

    def add_filter(self, filter):
        if not filter in self._filters:
            self._filters.append(filter)

    def _add_to(self, rule, group):
        if rule.get_pronunciation() in \
        self.global_rule_names()+\
        self.app_rule_names()+\
        self.selfmod_rule_names():
            raise Exception("Rule Naming Conflict: " + rule.get_pronunciation())
        if isinstance(rule, MergeRule):
            for name in group.keys():
                group[name].compatibility_check(
                    rule)  # calculate compatibility for uncombined rules at boot time
            group[rule.get_pronunciation()] = rule

    '''getters'''

    def global_rule_names(self):
        return self._global_rules.keys()

    def app_rule_names(self):
        return self._app_rules.keys()

    def selfmod_rule_names(self):
        return self._self_modifying_rules.keys()

    def display_rules(self):
        for rule in self.global_rule_names():
            if self._config[CCRMerger._GLOBAL][rule]:
                print("*" + rule)
            else:
                print(rule)

    '''rule change functions'''
    def global_rule_changer(self, name, enable, save):
        self._config[CCRMerger._GLOBAL][name] = enable
        self.merge(MergeInf.RUN, name, enable, save)
        print(name + " enabled" if enable else name + " disabled")

    def selfmod_rule_changer(self, name2, enable, save):
        self._config[CCRMerger._SELFMOD][name2] = enable
        self.merge(MergeInf.SELFMOD, name2, enable, save)

    '''merging'''

    def _get_rules_by_composite(self, composite, original=False):
        return [rule if original else rule.copy()  \
                for rule in self._global_rules.values() \
                if rule.ID in composite]

    def _compatibility_merge(self, merge_pair, base, rule):
        '''MergeRule.merge always returns a copy, so there's
        no need to worry about the originals getting modified'''
        if merge_pair.check_compatibility==False or \
        base is None or \
        base.compatibility_check(rule):
            base = rule if base is None else base.merge(rule)
        else:
            # figure out which MergeRules aren't compatible
            composite = base.composite.copy(
            )  # composite is a set of the ids of the rules which make up this rule
            for ID in rule.compatible:
                if not rule.compatible[ID]: composite.discard(ID)
            # rebuild a base from remaining MergeRules
            base = None
            for _rule in self._get_rules_by_composite(composite):
                base = _rule if base is None else base.merge(_rule)
            # merge in the new rule
            if base is not None:
                base = base.merge(rule)
            else:
                base = rule
        return base

    def _add_grammar(self, rule, ccr=False, context=None):
        name = str(rule)
        grammar = Grammar(name, context=context)
        self._grammars.append(grammar)
        if ccr:
            repeaters = self._create_repeat_rule(rule)
            for repeater in repeaters:
                grammar.add_rule(repeater)
        else:
            grammar.add_rule(rule)

    def wipe(self):
        while len(self._grammars) > 0:
            grammar = self._grammars.pop()
            for rule in grammar.rules:
                rule.disable()
            grammar.disable()
            del grammar

    def _sync_enabled(self):
        '''
        When enabling new rules, conflicting ones get automatically disabled.
        Throw these out of enabling order as well. Also prevent excessive size.
        '''
        if CCRMerger._ORDER not in self._config:
            self._config[CCRMerger._ORDER] = []
        enabled = [
            r for r in self._config[CCRMerger._ORDER]
            if self._config[CCRMerger._GLOBAL].get(r)][-100:]
        self._config[CCRMerger._ORDER] = OrderedDict(izip_longest(enabled, [])).keys()

    def merge(self, time, name=None, enable=True, save=False):
        '''combines MergeRules, SelfModifyingRules;
        handles CCR for apps;
        instantiates affiliated rules;
        adds everything to its grammar
        ;
        assumptions made:
        * SelfModifyingRules have already made changes to themselves
        * the appropriate activation boolean(s) in the appropriate map has already been set'''
        current_rule = None
        self.wipe()
        base = self._base_global
        named_rule = None
        '''get base CCR rule'''
        if time == MergeInf.BOOT:  # rebuild via config
            for name, rule in self._global_rules.iteritems():
                '''we want to be able to make permanent changes at boot time, not just
                to activated rules, but to everything -- but we dont' want it to interfere
                with normal merge logic-- hence the introduction of the BOOT_NO_MERGE time'''
                mp = MergePair(
                    MergeInf.BOOT_NO_MERGE, MergeInf.GLOBAL, None, rule, False
                )  # copies not made at boot time, allows user to make permanent changes
                self._run_filters(mp)

                if self._config[CCRMerger._GLOBAL][name]:
                    mp = MergePair(
                        time, MergeInf.GLOBAL, base, rule, False
                    )  # copies not made at boot time, allows user to make permanent changes
                    self._run_filters(mp)
                    if base is None: base = rule
                    else: base = self._compatibility_merge(mp, base, rule)
        else:  # rebuild via composite
            composite = base.composite.copy(
            )  # IDs of all rules that the composite rule is made of
            if time != MergeInf.SELFMOD:
                assert name is not None
                named_rule = self._global_rules[name]
                if enable is False:
                    composite.discard(named_rule.ID)  # throw out rule getting disabled
                else: # enable CCR rule
                    self._config[CCRMerger._ORDER].append(name)
                    current_rule = name
            base = None
            for rule in self._get_rules_by_composite(composite):
                mp = MergePair(time, MergeInf.GLOBAL, base, rule.copy(), False)
                self._run_filters(mp)
                if base is None: base = rule
                else:
                    base = self._compatibility_merge(
                        mp, base, mp.rule2)  # mp.rule2 because named_rule got copied
            if time != MergeInf.SELFMOD and enable == True:
                mp = MergePair(time, MergeInf.GLOBAL, base, named_rule.copy(), True)
                self._run_filters(mp)
                base = self._compatibility_merge(
                    mp, base, mp.rule2)  # mp.rule2 because named_rule got copied
        '''compatibility check and filter function active selfmodrules'''
        for name2, rule in self._self_modifying_rules.iteritems():
            '''no need to make copies of selfmod rules because even if
            filter functions trash their mapping, they'll just regenerate
            it next time they modify themselves;
            furthermore, they need to preserve state'''
            if self._config[CCRMerger._SELFMOD][name2]:
                mp = MergePair(time, MergeInf.SELFMOD, base, rule, False)
                self._run_filters(mp)
                base = self._compatibility_merge(mp, base, rule)
        '''have base, make copies, merge in apps'''
        active_apps = []
        for rule in self._app_rules.values():
            base_copy = base.copy() if base is not None else base
            # make a copy b/c commands will get stripped out
            context = rule.get_context()
            non_copy = rule.non if rule.non else None
            compounds_copy = rule.compounds if rule.compounds else None
            mp = MergePair(time, MergeInf.APP, base_copy, rule.copy(), False,
                           CCRMerger.specs_per_rulename(self._global_rules))
            self._run_filters(mp)
            rule = self._compatibility_merge(
                mp, base_copy, mp.rule2)  # mp.rule2 because named_rule got copied
            rule.non = non_copy
            rule.compounds = compounds_copy
            rule.set_context(context)
            active_apps.append(rule)
        '''negation context for appless version of base rule'''
        contexts = [app_rule.get_context() for app_rule in self._app_rules.values() \
                    if app_rule.get_context() is not None]# get all contexts
        negation_context = None
        for context in contexts:
            negate = ~context
            if negation_context is None: negation_context = negate
            else: negation_context & negate
        '''handle empty merge'''
        if base is None:
            base = MergeRule()
        ''' save results for next merge '''
        self._base_global = base.copy()
        '''instantiate non-ccr rules affiliated with rules in the base CCR rule'''
        active_global = self._get_rules_by_composite(base.composite, True)
        global_non_ccr = [rule.non() for rule in active_global \
                         if rule.non is not None]
        '''update grammars'''
        self._add_grammar(base, True, negation_context)
        for rule in global_non_ccr:
            self._add_grammar(rule)
        for rule in active_apps:
            self._add_grammar(rule, True, rule.get_context())
            if rule.non is not None:
                self._add_grammar(rule.non(), False, rule.get_context())
        for grammar in self._grammars:
            grammar.load()
        '''save if necessary'''
        if time in [MergeInf.RUN, MergeInf.SELFMOD] and save:
            # everything in base composite is active, everything in selfmod is active, update the config as such
            active_global_names = [rule.get_pronunciation() for rule in active_global]
            for rule_name in self._global_rules:
                self._config[CCRMerger._GLOBAL][
                    rule_name] = rule_name in active_global_names
            active_selfmod_names = [
                name3 for name3 in self._config[CCRMerger._SELFMOD]
                if self._config[CCRMerger._SELFMOD][name3]
            ]  #[rule.get_pronunciation() for rule in selfmod]
            for rule_name in self._self_modifying_rules:
                self._config[CCRMerger._SELFMOD][
                    rule_name] = rule_name in active_selfmod_names
        self._sync_enabled()
        if len(self._config[CCRMerger._ORDER]) > 0:
            current_rule = self._config[CCRMerger._ORDER][-1]
        # self._apply_format(current_rule)
        if save:
            self.save_config()

    @staticmethod
    def specs_per_rulename(d):
        result = {}
        for rulename in d.keys():
            rule = d[rulename]
            specs = rule.mapping_actual().keys()
            result[rulename] = specs
        return result

    def _run_filters(self, merge_pair):
        for filter_fn in self._filters:
            try:
                filter_fn(merge_pair)
            except Exception:
                print("Filter function '" + filter_fn.__name__ + "' failed.")

    def _create_repeat_rule(self, rule):
        ORIGINAL, SEQ, TERMINAL = "original", "caster_base_sequence", "terminal"
        alts = [RuleRef(rule=rule)]  #+[RuleRef(rule=sm) for sm in selfmod]
        single_action = Alternative(alts)
        max = SETTINGS["max_ccr_repetitions"]
        sequence = Repetition(single_action, min=1, max=max, name=SEQ)
        original = Alternative(alts, name=ORIGINAL)
        terminal = Alternative(alts, name=TERMINAL)

        class RepeatRule(CompoundRule):
            spec = "[<" + ORIGINAL + "> original] [<" + SEQ + ">] [terminal <" + TERMINAL + ">]"
            extras = [sequence, original, terminal]

            def _process_recognition(self, node, extras):
                original = extras[ORIGINAL] if ORIGINAL in extras else None
                sequence = extras[SEQ] if SEQ in extras else None
                terminal = extras[TERMINAL] if TERMINAL in extras else None
                if original is not None: original.execute()
                if sequence is not None:
                    for action in sequence:
                        action.execute()
                if terminal is not None: terminal.execute()

        rules = []
        rules.append(RepeatRule(name="Repeater" + MergeRule.get_merge_name()))

        '''
        compounds is a dictionary in a merge rule which maps a specification to a list of three dragonfly actions.
        The specification must include <sequence1> and <sequence2>, <before> and <after> are optional and allow for other commands to be spoken before or after the rule.
        Example command:
        "[<before>] integral from <sequence1> to <sequence2>":
                    [Text("\\int _"), Key("right, caret"), Key("right")],

        Any commands which come before will be executed first, then the first action in the list, then the first sequence, then the second action in the list, then the second sequence, then the final action.  At the moment sequences have a maximum length of 4 commands and before and after 8.
        '''
        if rule.compounds:
            class ReferenceRule(CompoundRule):
                def __init__(self, action_list=[], name=None, spec=None, extras=None, defaults=None, exported=None, context=None):
                    self.action_list = action_list
                    CompoundRule.__init__(self, name=name, spec=spec, extras=extras, defaults=defaults, exported=exported, context=context)

                def _process_recognition(self, node, extras):
                    if "before" in extras:
                        for action in extras["before"]: action.execute()
                    self.action_list[0].execute()
                    for action in extras["sequence1"]: action.execute()
                    self.action_list[1].execute()
                    for action in extras["sequence2"]: action.execute()
                    self.action_list[2].execute()
                    if "after" in extras:
                        for action in extras["after"]: action.execute()

            bef  = Repetition(single_action, min=1, max=8, name="before")
            aft  = Repetition(single_action, min=1, max=8, name="before")
            seq1 = Repetition(single_action, min=1, max=6, name="sequence1")
            seq2 = Repetition(single_action, min=1, max=6, name="sequence2")

            for command, action_list in rule.compounds.iteritems():
                rules.append(ReferenceRule(action_list=action_list,
                    name="ReferenceRule: " + command,
                    spec=command,
                    extras=[bef, aft, seq1, seq2]))

        return rules