from setuptools import setup, find_packages


version = '0.1.8'

setup(name="helga-versionone",
      version=version,
      description=('VersionOne interface for helga chat bot'),
      classifiers=[
          'Development Status :: 4 - Beta',
          'Topic :: Communications :: Chat :: Internet Relay Chat',
          'Framework :: Twisted',
          'License :: OSI Approved :: MIT License',
          'Operating System :: OS Independent',
          'Programming Language :: Python',
          'Programming Language :: Python :: 2',
          'Programming Language :: Python :: 2.6',
          'Programming Language :: Python :: 2.7',
          'Topic :: Software Development :: Libraries :: Python Modules',
      ],
      keywords='helga versionone',
      author='Aaron McMillin',
      author_email='aaron@mcmillinclan.org',
      url='https://github.com/aarcro/helga-versionone',
      download_url='https://github.com/aarcro/helga-versionone/tarball/' + version,
      license='MIT',
      packages=find_packages(),
      py_modules=['helga_versionone'],
      install_requires=[
          'v1pysdk-unofficial',
          'oauth2client',
          'expiringdict',
      ],
      entry_points = dict(
          helga_plugins=[
              'versionone = helga_versionone:versionone'
          ],
      ),
)
