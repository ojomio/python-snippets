class class_with_session:
    def __init__(self, func):

        self.exceptions_tuple = (Exception,)
        self.on_exception_handler = None

        def wrapper(*args, **kw):
            session = get_sa_session()
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