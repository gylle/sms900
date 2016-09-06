""" Create indexes for the on-disk media files """
import cgi
import datetime
import logging
from os import listdir, path

from jinja2 import Environment, FileSystemLoader

class Indexer():
    def __init__(self):
        self.env = env = Environment(
            loader=FileSystemLoader(searchpath="html/" )
        )

    def generate_local_index(self, base_path):
        mms = self._get_local_files(base_path)

        template = self.env.get_template("local-index.html")
        index_path = path.join(base_path, "index.html")
        self._write_file(
            template.render(
                ctime = mms['ctime'],
                images = mms['images'],
                texts = mms['texts'],
                all_files = mms['all_files']
            ),
            index_path
        )

    def generate_global_index(self, base_path, filename = "mms.html"):
        all_mms = []

        for f in listdir(base_path):
            local_path = path.join(base_path, f)
            if not path.isdir(local_path):
                continue

            mms = self._get_local_files(
                local_path,
                prepend_path = f
            )

            if not len(mms['all_files']):
                continue

            all_mms.append(mms)

        all_mms = sorted(all_mms, key = lambda mms: mms['ctime'], reverse = True)

        template = self.env.get_template("global-index.html")
        index_path = path.join(base_path, filename)
        self._write_file(
            template.render(
                all_mms = all_mms
            ),
            index_path
        )

    def reindex_all(self, base_path):
        for f in listdir(base_path):
            full_path = path.join(base_path, f)
            if path.isdir(full_path):
                self.generate_local_index(full_path)

        self.generate_global_index(base_path)

    def _get_local_files(self, local_path, prepend_path = None):
        images = []
        texts = []
        all_files = []
        ctime = None

        for f in listdir(local_path):
            full_path = path.join(local_path, f)
            if not path.isfile(full_path):
                continue

            if f == 'index.html':
                continue

            if not ctime:
                ctime = datetime.datetime.fromtimestamp(
                    path.getctime(full_path)
                ).strftime('%Y-%m-%d %H:%M:%S')

            file_info = {
                'name': f,
                'relpath': path.join(prepend_path, f) if prepend_path else f
            }

            all_files.append(file_info)

            ext = path.splitext(f)[1]
            if ext in ['.jpg', '.jpeg', '.png', '.gif']:
                images.append(file_info)
            elif ext in ['.txt']:
                try:
                    with open(full_path, 'r') as f:
                        data = cgi.escape(f.read())
                        texts.append(
                            "<br>".join(data.splitlines())
                        )
                except OSError:
                    logging.exception("Failed to read file %s" % full_path)

        return {
            'relpath': prepend_path,
            'ctime': ctime,
            'images': images,
            'texts': texts,
            'all_files': all_files
        }

    def _write_file(self, data, path):
        with open(path, 'w') as f:
            f.write(data)
