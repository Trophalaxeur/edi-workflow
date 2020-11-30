##############################################################################
#!/usr/bin/python
# -*- coding: utf-8 -*-
##############################################################################
USER=odoo
pip install 'django<1.8'
pip install 'cherrypy<8.0'
pip install genshi
wget -O bots-3.2.0.tar.gz http://sourceforge.net/projects/bots/files/bots%20open%20source%20edi%20software/3.2.0/bots-3.2.0.tar.gz/download
tar -xf bots-3.2.0.tar.gz
cd bots-3.2.0
python setup.py install
cd ..

#set rigths for bots directory to non-root:
chown -R $USER /usr/lib/python2.7/site-packages/bots
chown -R $USER /usr/local/lib/python2.7/dist-packages/bots

