'''
Created on 06.02.2011

@author: Gunnar
'''

from sbnc import client

listener = client.ClientListener( ('0.0.0.0', 9000) )
task = listener.start()

task.join()