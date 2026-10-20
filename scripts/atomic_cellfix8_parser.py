"""Keep LMFE's bounded-string fast path from bypassing character constraints."""
from lmformatenforcer import CharacterLevelParser
import lmformatenforcer.jsonschemaparser as _js
from lmformatenforcer.tokenizerprefixtree import JsonFreetextTokenCache
from copy import copy
import re


# LMFE 0.11.3 pushes the first item parser even for maxItems=0. Compile that
# supported JSON value literally, just as the existing boolean-const adapter.
if not getattr(_js.get_parser, '_atomic_empty_array_fix', False):
    _previous_get_parser = _js.get_parser

    def _empty_array_parser(state, schema, _previous=_previous_get_parser):
        if schema is not None and schema.type == 'array' and schema.maxItems == 0:
            return _js.StringParsingState(state, ['[]'], False, False)
        return _previous(state, schema)

    _empty_array_parser._atomic_empty_array_fix = True
    _js.get_parser = _empty_array_parser


class CheckedParser(CharacterLevelParser):
    def __init__(self, parser, config=None, filtered_cache=False):
        super().__init__(config or parser.config)
        self.parser = parser
        self.filtered_cache = filtered_cache

    def add_character(self, character):
        if character not in self.parser.get_allowed_characters():
            raise ValueError('Character violates the current JSON state')
        return CheckedParser(self.parser.add_character(character), self.config, self.filtered_cache)

    def get_allowed_characters(self):
        return self.parser.get_allowed_characters()

    def can_end(self):
        return self.parser.can_end()

    def shortcut_key(self):
        key = self.parser.shortcut_key()
        if self.filtered_cache and key and self.no_pending_whitespace(self.parser):
            return key
        return None

    @staticmethod
    def no_pending_whitespace(parser):
        if isinstance(parser, _js.JsonSchemaParser):
            return parser.num_consecutive_whitespaces == 0
        children = getattr(parser, 'parsers', [])
        return bool(children) and all(CheckedParser.no_pending_whitespace(p) for p in children)


def alphabet_tree(tree, config):
    """Share the vocabulary trie; replace only the request's free-text cache."""
    scoped = copy(tree)
    previous = tree.json_freetext_tokens
    cache = JsonFreetextTokenCache(previous.use_bitmask, previous.vocab_size)
    alphabet = set(config.alphabet) | {'\\'}
    excessive_whitespace = re.compile(r'[ \t\r\n]{'+str(config.max_consecutive_whitespaces+1)+r'}')
    for token, text in tree.tokens_to_strs.items():
        if set(text) <= alphabet and not excessive_whitespace.search(text):
            cache.add_token(text, token)
    cache.freeze()
    scoped.json_freetext_tokens = cache
    return scoped
