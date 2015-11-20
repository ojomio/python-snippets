import functools

from collections import Iterable
from warnings import warn

from sqlalchemy.dialects.postgresql import array
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.sql import FromClause, ClauseElement, bindparam
from sqlalchemy.sql.sqltypes import NULLTYPE


class class_with_session:
    def __init__(self, func):

        self.exceptions_tuple = (Exception,)
        self.on_exception_handler = None

        def wrapper(*args, **kw):
            session = Session()
            if session.transaction is None:
                session.begin()
            try:
                ret = func(db_session=session, *args, **kw)
                session.commit()
                return ret
            except self.exceptions_tuple as e:
                session.rollback()
                if self.on_exception_handler:
                    try:
                        handler_res = self.on_exception_handler(e)
                    except:
                        raise
                    else:
                        warn('Handler swallowed exception "%s"' % str(e))
                        return handler_res
                else:
                    raise

        self.func = wrapper

    def __get__(self, instance, class_):
        '''Перехват для методов'''
        return functools.partial(self.func, instance)

    def __set__(self, instance, value):
        '''Сделаем его non-data descriptor'''
        pass

    def __call__(self, *args, **kwargs):
        '''Перехват для функций'''
        return self.func(*args, **kwargs)

    def on_exception(self, exceptions_tuple=None):
        if exceptions_tuple:
            exceptions_tuple = tuple(exceptions_tuple) \
                if isinstance(exceptions_tuple, Iterable) \
                else (exceptions_tuple,)

            self.exceptions_tuple = exceptions_tuple

        def deco(fn):
            self.on_exception_handler = fn
            return fn

        return deco


def with_session(fn):
    '''
    Начинает транзакцию, если ещё не начата
    Если в функции происходит исключение(по умолчанию - любое), откатывает её
    '''
    return class_with_session(fn)


class values(FromClause):
    named_with_column = True

    def __init__(self, columns, *args, **kw):
        self._column_args = columns
        self.list = args
        self.alias_name = self.name = kw.pop('alias_name', None)

    def _populate_column_collection(self):
        # self._columns.update((col.name, col) for col in self._column_args)
        for c in self._column_args:
            c._make_proxy(self, c.name)


@compiles(values)
def compile_values(clause, compiler, asfrom=False, **kw):
    def decide(value, column):
        add_type_hint = False
        if isinstance(value, array) and not value.clauses:  # for empty array literals
            add_type_hint = True

        if isinstance(value, ClauseElement):
            intermediate = compiler.process(value)
            if add_type_hint:
                intermediate += '::' + str(column.type)
            return intermediate

        else:
            intermediate = compiler.render_literal_value(
                value,
                column.type if (value is not None) else NULLTYPE
            )
            if value is not None:
                intermediate = compiler.process(
                    bindparam(None, value=intermediate)
                ) + '::' + str(column.type)
            return intermediate

    columns = clause.columns
    v = "VALUES %s" % ", ".join(
        "(%s)" % ", ".join(
            decide(elem, column)
            for elem, column in zip(tup, columns))
        for tup in clause.list
    )
    if asfrom:
        if clause.alias_name:
            v = "(%s) AS %s (%s)" % (v, clause.alias_name, (", ".join(c.name for c in clause.columns)))
        else:
            v = "(%s)" % v
    return v
