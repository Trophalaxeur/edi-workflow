import base64
import hashlib
import logging
import re
import time
from odoo import api
import odoo.release as release
from odoo.tools.translate import _

_logger = logging.getLogger(__name__)

EXTERNAL_ID_PATTERN = re.compile(r'^([^.:]+)(?::([^.]+))?\.(\S+)$')
EDI_VIEW_WEB_URL = '%s/edi/view?db=%s&token=%s'
EDI_PROTOCOL_VERSION = 1  # arbitrary ever-increasing version number
EDI_GENERATOR = 'Odoo' + release.major_version
EDI_GENERATOR_VERSION = release.version_info


def split_external_id(ext_id):
    match = EXTERNAL_ID_PATTERN.match(ext_id)
    assert match, \
        _("'%s' is an invalid external ID") % (ext_id)
    return {'module': match.group(1),
            'db_uuid': match.group(2),
            'id': match.group(3),
            'full': match.group(0)}


def safe_unique_id(database_id, model, record_id):
    """Generate a unique string to represent a (database_uuid,model,record_id) pair
    without being too long, and with a very low probability of collisions.
    """
    msg = "%s-%s-%s-%s" % (time.time(), database_id, model, record_id)
    digest = hashlib.sha1(msg.encode('utf-8')).digest()
    # fold the sha1 20 bytes digest to 9 bytes
    digest = ''.join(chr(x ^ y) for (x, y) in zip(digest[:9], digest[9:-2]))
    # b64-encode the 9-bytes folded digest to a reasonable 12 chars ASCII ID
    digest = base64.urlsafe_b64encode(digest.encode('utf-8'))
    return '%s-%s' % (model.replace('.', '_'), digest)


def last_update_for(record):
    """Returns the last update timestamp for the given record,
       if available, otherwise False
    """
    if record._log_access:
        record_log = record.get_metadata()[0]
        return record_log.get('write_date') or record_log.get('create_date') or False
    return False


class EDIMixin(object):
    """Mixin class for Model objects that want be exposed as EDI documents.
       Classes that inherit from this mixin class should override the
       ``edi_import()`` and ``edi_export()`` methods to implement their
       specific behavior, based on the primitives provided by this mixin."""

    def _edi_requires_attributes(self, attributes, edi):
        model_name = edi.get('__imported_model') or edi.get('__model') or self._name
        for attribute in attributes:
            assert edi.get(attribute), \
                'Attribute `%s` is required in %s EDI documents.' % (attribute, model_name)

    # private method, not RPC-exposed as it creates ir.model.data entries as
    # SUPERUSER based on its parameters
    def _edi_external_id(self, record, existing_id=None, existing_module=None):
        """Generate/Retrieve unique external ID for ``record``.
        Each EDI record and each relationship attribute in it is identified by a
        unique external ID, which includes the database's UUID, as a way to
        refer to any record within any Odoo instance, without conflict.
        For Odoo records that have an existing "External ID" (i.e. an entry in
        ir.model.data), the EDI unique identifier for this record will be made of
        "%s:%s:%s" % (module, database UUID, ir.model.data ID). The database's
        UUID MUST NOT contain a colon characters (this is guaranteed by the
        UUID algorithm).
        For records that have no existing ir.model.data entry, a new one will be
        created during the EDI export. It is recommended that the generated external ID
        contains a readable reference to the record model, plus a unique value that
        hides the database ID. If ``existing_id`` is provided (because it came from
        an import), it will be used instead of generating a new one.
        If ``existing_module`` is provided (because it came from
        an import), it will be used instead of using local values.
        :param browse_record record: any browse_record needing an EDI external ID
        :param string existing_id: optional existing external ID value, usually coming
                                   from a just-imported EDI record, to be used instead
                                   of generating a new one
        :param string existing_module: optional existing module name, usually in the
                                       format ``module:db_uuid`` and coming from a
                                       just-imported EDI record, to be used instead
                                       of local values
        :return: the full unique External ID to use for record
        """
        ir_model_data = self.env['ir.model.data']
        db_uuid = self.env['ir.config_parameter'].get_param('database.uuid')
        ext_id = record.get_external_id()[record.id]
        if not ext_id:
            ext_id = existing_id or safe_unique_id(db_uuid, record._name, record.id)
            # ID is unique cross-db thanks to db_uuid (already included in existing_module)
            module = existing_module or "%s:%s" % (record._original_module, db_uuid)
            _logger.debug("%s: Generating new external ID `%s.%s` for %r.", self._name,
                          module, ext_id, record)
            ir_model_data.sudo().create({'name': ext_id,
                                         'model': record._name,
                                         'module': module,
                                         'res_id': record.id})
        else:
            module, ext_id = ext_id.split('.')
            if not ':' in module:
                # this record was not previously EDI-imported
                if not module == record._original_module:
                    # this could happen for data records defined in a module that depends
                    # on the module that owns the model, e.g. purchase defines
                    # product.pricelist records.
                    _logger.debug('Mismatching module: expected %s, got %s, for %s.',
                                  module, record._original_module, record)
                # ID is unique cross-db thanks to db_uuid
                module = "%s:%s" % (module, db_uuid)

        return '%s.%s' % (module, ext_id)

    def _edi_record_display_action(self, id):
        """Returns an appropriate action definition dict for displaying
           the record with ID ``rec_id``.
           :param int id: database ID of record to display
           :return: action definition dict
        """
        return {'type': 'ir.actions.act_window',
                'view_mode': 'form,tree',
                'view_type': 'form',
                'res_model': self._name,
                'res_id': id}

    def edi_metadata(self, records):
        """Return a list containing the boilerplate EDI structures for
           exporting ``records`` as EDI, including
           the metadata fields
        The metadata fields always include::
            {
               '__model': 'some.model',                # record model
               '__module': 'module',                   # require module
               '__id': 'module:db-uuid:model.id',      # unique global external ID for the record
               '__last_update': '2011-01-01 10:00:00', # last update date in UTC!
               '__version': 1,                         # EDI spec version
               '__generator' : 'Odoo',              # EDI generator
               '__generator_version' : [6,1,0],        # server version, to check compatibility.
               '__attachments_':
           }
        :param list(browse_record) records: records to export
        :return: list of dicts containing boilerplate EDI metadata for each record,
                 at the corresponding index from ``records``.
        """
        ir_attachment = self.env['ir.attachment']
        results = []
        for record in records:
            ext_id = self._edi_external_id(record)
            edi_dict = {
                '__id': ext_id,
                '__last_update': last_update_for(record),
                '__model': record._name,
                '__module': record._original_module,
                '__version': EDI_PROTOCOL_VERSION,
                '__generator': EDI_GENERATOR,
                '__generator_version': EDI_GENERATOR_VERSION,
            }
            attachment_ids = ir_attachment.search([('res_model', '=', record._name), ('res_id', '=', record.id)])
            if attachment_ids:
                attachments = []
                for attachment in attachment_ids:
                    attachments.append({
                        'name': attachment.name,
                        'content': attachment.datas,  # already base64 encoded!
                        'file_name': attachment.datas_fname,
                    })
                edi_dict.update(__attachments=attachments)
            results.append(edi_dict)
        return results

    def edi_m2o(self, record):
        """Return a m2o EDI representation for the given record.
        The EDI format for a many2one is::
            ['unique_external_id', 'Document Name']
        """
        edi_ext_id = self._edi_external_id(record)
        # relation_model = record._model
        name = record.name_get()
        name = name and name[0][1] or False
        return [edi_ext_id, name]

    def edi_o2m(self, records, edi_struct=None):
        """Return a list representing a O2M EDI relationship containing
           all the given records, according to the given ``edi_struct``.
           This is basically the same as exporting all the record using
           :meth:`~.edi_export` with the given ``edi_struct``, and wrapping
           the results in a list.
           Example::
             [                                # O2M fields would be a list of dicts, with their
               { '__id': 'module:db-uuid.id', # own __id.
                 '__last_update': 'iso date', # update date
                 'name': 'some name',
                 #...
               },
               # ...
             ],
        """
        result = []
        for record in records:
            result += record.edi_export([record], edi_struct=edi_struct)
        return result

    def edi_m2m(self, records, context=None):
        """Return a list representing a M2M EDI relationship directed towards
           all the given records.
           This is basically the same as exporting all the record using
           :meth:`~.edi_m2o` and wrapping the results in a list.
            Example::
                # M2M fields are exported as a list of pairs, like a list of M2O values
                [
                      ['module:db-uuid.id1', 'Task 01: bla bla'],
                      ['module:db-uuid.id2', 'Task 02: bla bla']
                ]
        """
        return [self.edi_m2o(r) for r in records]

    def edi_export(self, records, edi_struct=None):
        """Returns a list of dicts representing EDI documents containing the
           records, and matching the given ``edi_struct``, if provided.
           :param edi_struct: if provided, edi_struct should be a dictionary
                              with a skeleton of the fields to export.
                              Basic fields can have any key as value, but o2m
                              values should have a sample skeleton dict as value,
                              to act like a recursive export.
                              For example, for a res.partner record::
                                  edi_struct: {
                                       'name': True,
                                       'company_id': True,
                                       'address': {
                                           'name': True,
                                           'street': True,
                                           }
                                  }
                              Any field not specified in the edi_struct will not
                              be included in the exported data. Fields with no
                              value (False) will be omitted in the EDI struct.
                              If edi_struct is omitted, no fields will be exported
        """
        if edi_struct is None:
            edi_struct = {}
        fields_to_export = edi_struct.keys()
        results = []
        for record in records:
            edi_dict = self.edi_metadata([record])[0]
            for field_name in fields_to_export:
                field = self._fields[field_name]
                value = getattr(record, field_name)
                if not value and value not in ('', 0):
                    continue
                elif field.type == 'many2one':
                    value = self.edi_m2o(value)
                elif field.type == 'many2many':
                    value = self.edi_m2m(value)
                elif field.type == 'one2many':
                    value = self.edi_o2m(value, edi_struct=edi_struct.get(field_name, {}))
                edi_dict[field_name] = value
            results.append(edi_dict)
        return results

    def _edi_get_object_by_name(self, name, model_name):
        model = self.env[model_name]
        search_results = model.name_search(name, operator='=')
        if len(search_results) == 1:
            return model.browse(search_results[0][0])
        return False

    @api.model
    def _edi_generate_report_attachment(self, record):
        """Utility method to generate the first PDF-type report declared for the
           current model with ``usage`` attribute set to ``default``.
           This must be called explicitly by models that need it, usually
           at the beginning of ``edi_export``, before the call to ``super()``."""
        ir_actions_report = self.env['ir.actions.report']
        matching_report = ir_actions_report.search([('model', '=', self._name),
                                                     ('report_type', '=', 'pdf')],limit=1)
        if matching_report:
            report = matching_report
            result, format = report.render_qweb_pdf([record.id])
            eval_context = {'time': time, 'object': record}
            if not report.attachment or not eval(report.attachment, eval_context):
                # no auto-saving of report as attachment, need to do it manually
                result = base64.b64encode(result)
                file_name = record.name_get()[0][1]
                file_name = re.sub(r'[^a-zA-Z0-9_-]', '_', file_name)
                file_name += ".pdf"
                self.env['ir.attachment'].create(
                                                      {
                                                          'name': file_name,
                                                          'datas': result,
                                                          'datas_fname': file_name,
                                                          'res_model': self._name,
                                                          'res_id': record.id,
                                                          'type': 'binary'
                                                      },
                                                      )

    def _edi_import_attachments(self, cr, uid, record_id, edi, context=None):
        ir_attachment = self.env['ir.attachment']
        for attachment in edi.get('__attachments', []):
            # check attachment data is non-empty and valid
            file_data = None
            try:
                file_data = base64.b64decode(attachment.get('content'))
            except TypeError:
                pass
            assert file_data, 'Incorrect/Missing attachment file content.'
            assert attachment.get('name'), 'Incorrect/Missing attachment name.'
            assert attachment.get('file_name'), 'Incorrect/Missing attachment file name.'
            assert attachment.get('file_name'), 'Incorrect/Missing attachment file name.'
            ir_attachment.create({'name': attachment['name'],
                                           'datas_fname': attachment['file_name'],
                                           'res_model': self._name,
                                           'res_id': record_id,
                                           # should be pure 7bit ASCII
                                           'datas': str(attachment['content']),
                                           })

    def _edi_get_object_by_external_id(self, external_id, model, context=None):
        """Returns browse_record representing object identified by the model and external_id,
           or None if no record was found with this external id.
           :param external_id: fully qualified external id, in the EDI form
                               ``module:db_uuid:identifier``.
           :param model: model name the record belongs to.
        """
        ir_model_data = self.env['ir.model.data']
        # external_id is expected to have the form: ``module:db_uuid:model.random_name``
        ext_id_members = split_external_id(external_id)
        db_uuid = self.env['ir.config_parameter'].get_param('database.uuid')
        module = ext_id_members['module']
        ext_id = ext_id_members['id']
        modules = []
        ext_db_uuid = ext_id_members['db_uuid']
        if ext_db_uuid:
            modules.append('%s:%s' % (module, ext_id_members['db_uuid']))
        if ext_db_uuid is None or ext_db_uuid == db_uuid:
            # local records may also be registered without the db_uuid
            modules.append(module)
        data_ids = ir_model_data.search([('model', '=', model),
                                                  ('name', '=', ext_id),
                                                  ('module', 'in', modules)])
        if data_ids:
            model = self.env[model]
            data = data_ids[0]
            if model.exists([data.res_id]):
                return model.browse(data.res_id)
            # stale external-id, cleanup to allow re-import, as the corresponding record is gone
                data.unlink()

    def edi_import_relation(self, model, value, external_id):
        """Imports a M2O/M2M relation EDI specification ``[external_id,value]`` for the
           given model, returning the corresponding database ID:
           * First, checks if the ``external_id`` is already known, in which case the corresponding
             database ID is directly returned, without doing anything else;
           * If the ``external_id`` is unknown, attempts to locate an existing record
             with the same ``value`` via name_search(). If found, the given external_id will
             be assigned to this local record (in addition to any existing one)
           * If previous steps gave no result, create a new record with the given
             value in the target model, assign it the given external_id, and return
             the new database ID
           :param str value: display name of the record to import
           :param str external_id: fully-qualified external ID of the record
           :return: database id of newly-imported or pre-existing record
        """
        _logger.debug("%s: Importing EDI relationship [%r,%r]", model, external_id, value)
        target = self._edi_get_object_by_external_id(external_id, model)
        need_new_ext_id = False
        if not target:
            _logger.debug("%s: Importing EDI relationship [%r,%r] - ID not found, trying name_get.",
                          self._name, external_id, value)
            target = self._edi_get_object_by_name(value, model)
            need_new_ext_id = True
        if not target:
            _logger.debug("%s: Importing EDI relationship [%r,%r] - name not found, creating it.",
                          self._name, external_id, value)
            # also need_new_ext_id here, but already been set above
            model = self.env[model]
            res_id, _ = model.name_create(value)
            target = res_id
        else:
            _logger.debug("%s: Importing EDI relationship [%r,%r] - record already exists with ID %s, using it",
                          self._name, external_id, value, target.id)
        if need_new_ext_id:
            ext_id_members = split_external_id(external_id)
            # module name is never used bare when creating ir.model.data entries, in order
            # to avoid being taken as part of the module's data, and cleanup up at next update
            module = "%s:%s" % (ext_id_members['module'], ext_id_members['db_uuid'])
            # create a new ir.model.data entry for this value
            self._edi_external_id(target, existing_id=ext_id_members['id'], existing_module=module)
        return target.id

    def edi_import(self, edi):
        """Imports a dict representing an EDI document into the system.
           :param dict edi: EDI document to import
           :return: the database ID of the imported record
        """
        assert self._name == edi.get('__import_model') or \
               ('__import_model' not in edi and self._name == edi.get('__model')), \
            "EDI Document Model and current model do not match: '%s' (EDI) vs '%s' (current)." % \
            (edi.get('__model'), self._name)

        # First check the record is now already known in the database, in which case it is ignored
        ext_id_members = split_external_id(edi['__id'])
        existing = self._edi_get_object_by_external_id(ext_id_members['full'], self._name)
        if existing:
            _logger.info("'%s' EDI Document with ID '%s' is already known, skipping import!", self._name,
                         ext_id_members['full'])
            return existing.id

        record_values = {}
        o2m_todo = {}  # o2m values are processed after their parent already exists
        for field_name, field_value in edi.iteritems():
            # skip metadata and empty fields
            if field_name.startswith('__') or field_value is None or field_value is False:
                continue
            field = self._fields.get(field_name)
            if not field:
                _logger.warning('Ignoring unknown field `%s` when importing `%s` EDI document.', field_name, self._name)
                continue
            # skip function/related fields
            if not field.store:
                _logger.warning(
                    "Unexpected function field value is found in '%s' EDI document: '%s'." % (self._name, field_name))
                continue
            relation_model = field.comodel_name
            if field.type == 'many2one':
                record_values[field_name] = self.edi_import_relation(relation_model,
                                                                     field_value[1], field_value[0])
            elif field.type == 'many2many':
                record_values[field_name] = [self.edi_import_relation(relation_model, m2m_value[1], m2m_value[0])
                                             for m2m_value in field_value]
            elif field.type == 'one2many':
                # must wait until parent report is imported, as the parent relationship
                # is often required in o2m child records
                o2m_todo[field_name] = field_value
            else:
                record_values[field_name] = field_value

        module_ref = "%s:%s" % (ext_id_members['module'], ext_id_members['db_uuid'])
        record_id = self.env['ir.model.data']._update(self._name, module_ref, record_values,
                                                           xml_id=ext_id_members['id'])
        record = self.browse(record_id)
        record_display, = record.name_get()

        # process o2m values, connecting them to their parent on-the-fly
        for o2m_field, o2m_value in o2m_todo.iteritems():
            field = self._fields[o2m_field]
            dest_model = self.env[field.comodel_name]
            dest_field = field.inverse_name
            for o2m_line in o2m_value:
                # link to parent record: expects an (ext_id, name) pair
                o2m_line[dest_field] = (ext_id_members['full'], record_display[1])
                dest_model.edi_import(o2m_line)

        # process the attachments, if any
        self._edi_import_attachments(record_id, edi)

        return record_id

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
