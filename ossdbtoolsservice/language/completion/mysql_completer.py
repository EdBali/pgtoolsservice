import logging
from collections import Counter
from itertools import chain
from logging import Logger
from re import compile, escape

from prompt_toolkit.completion import Completer

from .mysql_completion import MySQLCompletion
from .packages.mysql_completion_engine import suggest_type
from .packages.mysqlliterals.main import get_literals
from .packages.parseutils.utils import find_prev_keyword, last_word


class MySQLCompleter(Completer):
    keywords_tree = get_literals('keywords', type_=dict)
    keywords = tuple(set(chain(keywords_tree.keys(), *keywords_tree.values())))
    functions = get_literals('functions')
    datatypes = get_literals('datatypes')
    reserved_words = set(get_literals('reserved'))

    show_items = []

    change_items = get_literals('change_items')

    users = []

    def __init__(self, smart_completion=True, logger=None, settings=None):
        super().__init__()
        self.smart_completion = smart_completion
        self.logger: Logger = logger
        settings = settings or {}

        self.reserved_words = set()
        for x in self.keywords:
            self.reserved_words.update(x.split())
        self.name_pattern = compile(r"^[_a-z][_a-z0-9\$]*$")

        keyword_casing = settings.get('keyword_casing', 'upper').lower()
        if keyword_casing not in ('upper', 'lower', 'auto'):
            keyword_casing = 'auto'
        self.keyword_casing = keyword_casing
        self.reset_completions()

    def _log(self, is_error: bool, msg: str, *args) -> None:
        if self.logger is not None:
            if is_error:
                self.logger.error(msg, *args)
            else:
                self.logger.debug(msg, *args)

    def escape_name(self, name):
        if name and ((not self.name_pattern.match(name))
                or (name.upper() in self.reserved_words)
                or (name.upper() in self.functions)):
                    name = '`%s`' % name

        return name

    def unescape_name(self, name):
        """Unquote a string."""
        if name and name[0] == '"' and name[-1] == '"':
            name = name[1:-1]

        return name

    def escaped_names(self, names):
        return [self.escape_name(name) for name in names]

    def extend_database_names(self, databases):
        self.databases.extend(databases)

    def extend_keywords(self, additional_keywords):
        keywords_list = list(self.keywords)
        keywords_list.extend(additional_keywords)
        self.keywords = tuple(keywords_list)
        self.all_completions.update(additional_keywords)

    def extend_show_items(self, show_items):
        for show_item in show_items:
            self.show_items.extend(show_item)
            self.all_completions.update(show_item)

    def extend_users(self, users):
        for user in users:
            self.users.extend(user)
            self.all_completions.update(user)

    def extend_schemata(self, schema):
        if schema is None:
            return
        metadata = self.dbmetadata['tables']
        metadata[schema] = {}

        # dbmetadata.values() are the 'tables' and 'functions' dicts
        for metadata in self.dbmetadata.values():
            metadata[schema] = {}
        self.all_completions.update(schema)

    def extend_relations(self, data, kind):
        """Extend metadata for tables or views

        :param data: list of (rel_name, ) tuples
        :param kind: either 'tables' or 'views'
        :return:
        """
        # 'data' is a generator object. It can throw an exception while being
        # consumed. This could happen if the user has launched the app without
        # specifying a database name. This exception must be handled to prevent
        # crashing.
        try:
            data = [self.escaped_names(d) for d in data]
        except Exception:
            data = []

        # dbmetadata['tables'][$schema_name][$table_name] should be a list of
        # column names. Default to an asterisk
        metadata = self.dbmetadata[kind]
        for relname in data:
            try:
                metadata[self.dbname][relname[0]] = ['*']
            except KeyError:
                self._log(True, '%r %r listed in unrecognized schema %r',
                              kind, relname[0], self.dbname)
            self.all_completions.add(relname[0])

    def extend_columns(self, column_data, kind):
        """Extend column metadata

        :param column_data: list of (rel_name, column_name) tuples
        :param kind: either 'tables' or 'views'
        :return:
        """
        # 'column_data' is a generator object. It can throw an exception while
        # being consumed. This could happen if the user has launched the app
        # without specifying a database name. This exception must be handled to
        # prevent crashing.
        try:
            column_data = [self.escaped_names(d) for d in column_data]
        except Exception:
            column_data = []

        metadata = self.dbmetadata[kind]
        for relname, column in column_data:
            metadata[self.dbname][relname].append(column)
            self.all_completions.add(column)

    def extend_functions(self, func_data):
        # 'func_data' is a generator object. It can throw an exception while
        # being consumed. This could happen if the user has launched the app
        # without specifying a database name. This exception must be handled to
        # prevent crashing.
        try:
            func_data = [self.escaped_names(d) for d in func_data]
        except Exception:
            func_data = []

        # dbmetadata['functions'][$schema_name][$function_name] should return
        # function metadata.
        metadata = self.dbmetadata['functions']

        for func in func_data:
            metadata[self.dbname][func[0]] = None
            self.all_completions.add(func[0])

    def set_dbname(self, dbname):
        self.dbname = dbname

    def reset_completions(self):
        self.databases = []
        self.users = []
        self.show_items = []
        self.dbname = ''
        self.dbmetadata = {'tables': {}, 'views': {}, 'functions': {}}
        self.all_completions = set(self.keywords + self.functions)

    def find_matches(self, text, collection, start_only=False, fuzzy=True, meta=None):
        """Find completion matches for the given text.

        Given the user's input text and a collection of available
        completions, find completions matching the last word of the
        text.

        If `start_only` is True, the text will match an available
        completion only at the beginning. Otherwise, a completion is
        considered a match if the text appears anywhere within it.

        yields prompt_toolkit Completion instances for any matches found
        in the collection of available completions.
        """
        last = last_word(text, include='most_punctuations')
        text = last.lower()

        completions = []

        if fuzzy:
            regex = '.*?'.join(map(escape, text))
            pat = compile('(%s)' % regex)
            for item in sorted(collection):
                r = pat.search(item.lower())
                if r:
                    completions.append((len(r.group()), r.start(), item))
        else:
            match_end_limit = len(text) if start_only else None
            for item in sorted(collection):
                match_point = item.lower().find(text, 0, match_end_limit)
                if match_point >= 0:
                    completions.append((len(text), match_point, item))

        if self.keyword_casing == 'auto':
            self.keyword_casing = 'lower' if last and last[-1].islower() else 'upper'

        def apply_case(kw):
            if self.keyword_casing == 'upper':
                return kw.upper()
            return kw.lower()

        return (MySQLCompletion(apply_case(z), -len(text), 
                display_meta=meta, schema=self.dbname)
                for x, y, z in sorted(completions))

    def get_completions(self, document, complete_event, smart_completion=None):
        word_before_cursor = document.get_word_before_cursor(WORD=True)
        if smart_completion is None:
            smart_completion = self.smart_completion

        # If smart_completion is off then match any word that starts with
        # 'word_before_cursor'.
        if not smart_completion:
            return self.find_matches(word_before_cursor, self.all_completions,
                                     start_only=True, fuzzy=False)

        completions = []
        suggestions = suggest_type(document.text, document.text_before_cursor)

        for suggestion in suggestions:

            self._log(False, 'Suggestion type: %r', suggestion['type'])

            if suggestion['type'] == 'column':
                tables = suggestion['tables']
                self._log(False, "Completion column scope: %r", tables)
                scoped_cols = self.populate_scoped_cols(tables)
                if suggestion.get('drop_unique'):
                    # drop_unique is used for 'tb11 JOIN tbl2 USING (...'
                    # which should suggest only columns that appear in more than
                    # one table
                    scoped_cols = [
                        col for (col, count) in Counter(scoped_cols).items()
                        if count > 1 and col != '*'
                    ]

                cols = self.find_matches(word_before_cursor, scoped_cols, meta='column')
                completions.extend(cols)

            elif suggestion['type'] == 'function':
                # suggest user-defined functions using substring matching
                funcs = self.populate_schema_objects(suggestion['schema'],
                                                     'functions')
                user_funcs = self.find_matches(word_before_cursor, funcs)
                completions.extend(user_funcs)

                # suggest hardcoded functions using startswith matching only if
                # there is no schema qualifier. If a schema qualifier is
                # present it probably denotes a table.
                # eg: SELECT * FROM users u WHERE u.
                if not suggestion['schema']:
                    predefined_funcs = self.find_matches(word_before_cursor,
                                                         self.functions,
                                                         start_only=True,
                                                         fuzzy=False,
                                                         meta='function')
                    completions.extend(predefined_funcs)

            elif suggestion['type'] == 'table':
                tables = self.populate_schema_objects(suggestion['schema'],
                                                      'tables')
                tables = self.find_matches(word_before_cursor, tables, meta='table')
                completions.extend(tables)

            elif suggestion['type'] == 'view':
                views = self.populate_schema_objects(suggestion['schema'],
                                                     'views')
                views = self.find_matches(word_before_cursor, views, meta='view')
                completions.extend(views)

            elif suggestion['type'] == 'alias':
                aliases = suggestion['aliases']
                aliases = self.find_matches(word_before_cursor, aliases, meta='alias')
                completions.extend(aliases)

            elif suggestion['type'] == 'database':
                dbs = self.find_matches(word_before_cursor, self.databases, meta='database')
                completions.extend(dbs)

            elif suggestion['type'] == 'keyword':
                keywords_suggestions = self.keywords_tree.keys()
                # Get well known following keywords for the last token. If any, narrow      
                # candidates to this list.
                next_keywords = self.keywords_tree.get(find_prev_keyword(document.text_before_cursor)[1], [])
                if next_keywords:
                    keywords_suggestions = next_keywords
                keywords = self.find_matches(word_before_cursor, keywords_suggestions,
                                            start_only=True,
                                            fuzzy=False,
                                            meta='keyword')
                completions.extend(keywords)

            elif suggestion['type'] == 'show':
                show_items = self.find_matches(word_before_cursor,
                                               self.show_items,
                                               start_only=False,
                                               fuzzy=True,
                                                meta='show')
                completions.extend(show_items)

            elif suggestion['type'] == 'change':
                change_items = self.find_matches(word_before_cursor,
                                                 self.change_items,
                                                 start_only=False,
                                                 fuzzy=True, meta='change')
                completions.extend(change_items)
            elif suggestion['type'] == 'user':
                users = self.find_matches(word_before_cursor, self.users,
                                          start_only=False,
                                          fuzzy=True, meta='user')
                completions.extend(users)

        return completions


    def populate_scoped_cols(self, scoped_tbls):
        """Find all columns in a set of scoped_tables
        :param scoped_tbls: list of (schema, table, alias) tuples
        :return: list of column names
        """
        columns = []
        meta = self.dbmetadata

        for tbl in scoped_tbls:
            # A fully qualified schema.relname reference or default_schema
            # DO NOT escape schema names.
            schema = tbl[0] or self.dbname
            relname = tbl[1]
            escaped_relname = self.escape_name(tbl[1])

            # We don't know if schema.relname is a table or view. Since
            # tables and views cannot share the same name, we can check one
            # at a time
            try:
                columns.extend(meta['tables'][schema][relname])

                # Table exists, so don't bother checking for a view
                continue
            except KeyError:
                try:
                    columns.extend(meta['tables'][schema][escaped_relname])
                    # Table exists, so don't bother checking for a view
                    continue
                except KeyError:
                    pass

            try:
                columns.extend(meta['views'][schema][relname])
            except KeyError:
                pass

        return columns

    def populate_schema_objects(self, schema, obj_type):
        """Returns list of tables or functions for a (optional) schema"""
        metadata = self.dbmetadata[obj_type]
        schema = schema or self.dbname

        try:
            objects = metadata[schema].keys()
        except KeyError:
            # schema doesn't exist
            objects = []

        return objects
