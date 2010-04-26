#!/usr/bin/env python

from distutils.core import setup

setup(
    name = "spark",
    version = "0.2.3",
    author = 'Wensheng Wang',
    author_email = 'wenshengwang@gmail.com',
    url = 'http://trac.wensheng.com/wiki/SparkProject',
    description = 'A Super-Small, Super-Fast, and Super-Easy web framework',
    long_description = 'A Super-Small, Super-Fast, and Super-Easy web framework',
    license = 'MIT',
    #download_url = 'http://pytan.com/public/spark.tgz',
    classifiers=[
          'Development Status :: 3 - Alpha',
          'Environment :: Web Environment',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: MIT License',
          'Operating System :: OS Independent',
          'Programming Language :: Python',
          'Topic :: Internet :: WWW/HTTP',
          'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
          'Topic :: Software Development :: Code Generators',
          'Topic :: Software Development :: Libraries :: Python Modules',
          'Topic :: Text Processing',
          ],
    packages = ['spark'],
    package_data = {'spark': [
	'contribs/*.py',
	'proj/webdir/*.py',
	'proj/etc/*',
	'proj/scripts/*.py',
	'proj/files/*',],
    },
    scripts = ['spark/bin/spark'],
)

