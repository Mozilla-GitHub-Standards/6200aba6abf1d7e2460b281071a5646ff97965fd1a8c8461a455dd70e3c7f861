from services.metrics import timeit

@timeit
def d_external_method(x, y):
    return x * y

@timeit(logger='kwarg external')
def d_external_kwarg_method(x, y):
    return x * y

class d_ExternalClass(object):
    @timeit
    def some_instance_method(self, x, y):
        return x * y

    @timeit(logger='instance logger')
    def some_kwarg_method(self, x, y):
        return x * y

