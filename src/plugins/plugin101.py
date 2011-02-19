from sbnc.plugin import Plugin, ServiceRegistry

class TestPlugin(Plugin):
    name = 'Test Plugin 101'
    description = 'Just a test plugin.'

    def __init__(self):
        proxy = ServiceRegistry.get('info.shroudbnc.services.proxy')
        
        user = proxy.create_user('shroud')
        user.password = 'keks'
        
ServiceRegistry.register('info.shroudbnc.plugins.plugin101', TestPlugin())
