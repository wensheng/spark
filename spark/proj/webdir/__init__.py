#1: display debug error info, 0:display 500 internal error
debug = 1

#define regular expression url patterns
#e.g. ['^$','foo'] means url / will be handled by module foo
#e.g. ['^car$','vehicle'] means url /car/ will be handled by module vehicle
#  ['^\d{4}\/\d{2}','blog','month'] means url /2006/02/ will be handled by
# "month" method in module "blog"
#the order is important, first match is honored.
#see document for more details
rewrites = [
]

admin = {
	"dbsetting":{
		'dbname':'',
		'user':'root',
		'password':'',
	},
	"rowsperpage":5,
	"tmpdir":'/tmp',
}

import os.path
#tmpl_dir is default template directory
#cache_dir is default cache directory
#you can overwrite them here, or you can define them in 
# individual controller
tmpl_dir = os.path.join(os.path.dirname(__file__),'..','templates')
cache_dir = os.path.join(os.path.dirname(__file__),'..','cache')
