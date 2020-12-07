##############################################################################
#!/usr/bin/python
# -*- coding: utf-8 -*-
##############################################################################
USER=odoo
BOTS_LIB_PATH=/usr/local/lib/python3.7/dist-packages/bots-3.3.1.dev0-py3.7.egg/bots
# pip install 'django<1.9'
# pip install 'cherrypy<8.0'
# pip install genshi
# wget -O bots-3.2.0.tar.gz http://sourceforge.net/projects/bots/files/bots%20open%20source%20edi%20software/3.2.0/bots-3.2.0.tar.gz/download
# tar -xf bots-3.2.0.tar.gz
# cd bots-3.2.0
# python setup.py install
# cd ..

#set rigths for bots directory to non-root:
# chown -R $USER /usr/lib/python2.7/site-packages/bots



cd bots
python3 setup.py install --record ../installed_files.txt
cd ..

cp bots-grammars/* $BOTS_LIB_PATH/usersys/grammars -r
#set rigths for bots directory to non-root:
chown -R $USER $BOTS_LIB_PATH