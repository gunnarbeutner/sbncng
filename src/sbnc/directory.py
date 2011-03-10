# sbncng - an object-oriented framework for IRC
# Copyright (C) 2011 Gunnar Beutner
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

import json
from uuid import uuid4
from sqlalchemy import create_engine, Column, Integer, \
    String, ForeignKey, Index, types, orm
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, backref, sessionmaker
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.schema import UniqueConstraint
from sbnc.plugin import Service, ServiceRegistry

_ModelBase = declarative_base()

class _JSONString(types.TypeDecorator):
    """Converts arbitrary Python objects to/from JSON."""

    impl = types.String

    def process_bind_param(self, value, dialect):
        if value != None:
            return json.dumps(value)
        else:
            return None

    def process_result_value(self, value, dialect):
        if value != None:
            return json.loads(value)
        else:
            return None

class Attribute(_ModelBase):
    """A key-value pair that belongs to a node."""

    __tablename__ = 'attributes'

    id = Column(Integer, primary_key=True)
    node_id = Column(Integer, ForeignKey('nodes.id'), nullable=False)
    key = Column(String(128), nullable=False)
    value = Column(_JSONString)

    def __init__(self, node, key, value=None):
        self.node = node
        self.key = key
        self.value = value

        self.init_on_load()
        
    @orm.reconstructor
    def init_on_load(self):
        dir_svc = ServiceRegistry.get(DirectoryService.package)
        self._session = dir_svc.get_session()
    
    def __repr__(self):
        return "<attribute key %s, value %s>" % (repr(self.key), repr(self.value))

Index('idx_attributes_1', Attribute.node_id)
UniqueConstraint(Attribute.node_id, Attribute.key)

class Node(_ModelBase):
    """A node in a tree-based directory that can have attributes and child nodes."""

    __tablename__ = 'nodes'

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey('nodes.id'))
    name = Column(String(128), nullable=False)

    children = relationship('Node', backref=backref('parent', remote_side=id), cascade='all')
    """Returns a list of child nodes."""

    attributes = relationship(Attribute, backref=backref('node'), \
                              cascade='all', order_by=Attribute.id)
    """Returns a list of attributes, in the same order like they were inserted in."""

    def __init__(self, name, parent=None):
        self.parent = parent
        self.name = name
        
        self.init_on_load()
        
    @orm.reconstructor
    def init_on_load(self):
        dir_svc = ServiceRegistry.get(DirectoryService.package)
        self._session = dir_svc.get_session()

    def __getitem__(self, name):
        """Retrieves the specified child node."""
        
        if not isinstance(name, basestring):
            return self.children[name]

        try:
            node = self._session.query(Node).filter_by(name=name, parent=self).one()
        except NoResultFound:
            node = Node(name, parent=self)
            self._session.add(node)
            self._session.commit()

        return node

    def __delitem__(self, name):
        """Removes the specified child node."""

        self._session.query(Node).filter_by(name=name, parent=self).delete()
        self._session.commit()

    def get(self, key, default_value):
        """Retrieves the value associated with the specified attribute."""

        try:
            attrib = self._session.query(Attribute).filter_by(node=self, key=key).one()
            return attrib.value
        except NoResultFound:
            self.set(key, default_value)
            return default_value

    def set(self, key, value):
        """Sets an attribute."""

        try:
            attrib = self._session.query(Attribute).filter_by(node=self, key=key).one()
        except NoResultFound:
            attrib = Attribute(self, key, value)
            self._session.add(attrib)
            self._session.commit()

    def unset(self, key):
        """Removes the specified attribute."""

        self._session.query(Attribute).filter_by(node=self, key=key).delete()

    def append(self, value):
        """Creates a new attribute using a randomly generated key and the specified value."""

        key = str(uuid4())
        self.set(key, value)

        return key

    def clear(self):
        """Removes all attributes."""

        self._session.query(Attribute).filter_by(node=self).delete()
        self._session.commit()

    def __repr__(self):
        return "<node name %s, parent %s>" % \
                (repr(self.name), repr(self.parent))

Index('idx_nodes_1', Node.parent_id)
UniqueConstraint(Node.parent_id, Node.name)

class DirectoryService(Service):
    package = 'info.shroudbnc.services.directory'
    
    def __init__(self):
        self._session = None
    
    def start(self, dsn, debug=False):
        """Initializes a database connection for the specified connection string."""
    
        engine = create_engine(dsn, echo=debug)
    
        metadata = _ModelBase.metadata
        metadata.create_all(engine)
    
        SessionClass = sessionmaker(bind=engine)
    
        self._session = SessionClass()
    
        try:
            root = self._session.query(Node).filter_by(name='root', parent=None).one()
        except NoResultFound:
            root = Node('root')
            self._session.add(root)
    
        self._root_node = root
    
    def get_session(self):
        return self._session
    
    def get_root_node(self):
        return self._root_node

ServiceRegistry.register(DirectoryService)
