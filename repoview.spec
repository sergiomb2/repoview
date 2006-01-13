# $Id$

Name:           repoview
Version:        0.5
Release:        1
Summary:        Creates a set of static HTML pages in a yum repository.

Group:          Applications/System
License:        GPL
URL:            http://linux.duke.edu/projects/mini/%{name}
Source0:        http://linux.duke.edu/projects/mini/%{name}/download/%{name}-%{version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-root
BuildArch:      noarch

Requires:       python >= 2.2, python-kid >= 0.6.3, yum >= 2.3

%description
RepoView creates a set of static HTML pages in a yum repository for easy
browsing.


%prep
%setup -q
##
# Fix version and default templates dir.
#
sed -i -e \
    "s|^VERSION =.*|VERSION = '%{version}-%{release}'|g" repoview.py
sed -i -e \
    "s|^DEFAULT_TEMPLATEDIR =.*|DEFAULT_TEMPLATEDIR = '%{_datadir}/%{name}/templates'|g" \
    repoview.py

%install
rm -rf $RPM_BUILD_ROOT
mkdir -p -m 755                         \
    $RPM_BUILD_ROOT/%{_datadir}/%{name} \
    $RPM_BUILD_ROOT/%{_bindir}          \
    $RPM_BUILD_ROOT/%{_mandir}/man8
install -m 755 repoview.py  $RPM_BUILD_ROOT/%{_bindir}/repoview
install -m 644 repoview.8   $RPM_BUILD_ROOT/%{_mandir}/man8/
cp -a templates             $RPM_BUILD_ROOT/%{_datadir}/%{name}/


%clean
rm -rf $RPM_BUILD_ROOT


%files
%defattr(-,root,root,-)
%doc README COPYING ChangeLog
%{_datadir}/%{name}
%{_bindir}/*
%{_mandir}/man*/*


%changelog
* Fri Jan 13 2006 Konstantin Ryabitsev <icon@fedoraproject.org> - 0.5-1
- Version 0.5

* Fri Oct 07 2005 Konstantin Ryabitsev <icon@linux.duke.edu> - 0.4.1-1
- Version 0.4.1

* Fri Sep 23 2005 Konstantin Ryabitsev <icon@linux.duke.edu> - 0.4-1
- Version 0.4
- Add yum >= 2.3 requirement
- Drop python-elementtree dependency, since it's required by yum

* Fri Mar 25 2005 Konstantin Ryabitsev <icon@linux.duke.edu> 0.3-1
- Version 0.3

* Thu Mar 10 2005 Konstantin Ryabitsev <icon@linux.duke.edu> 0.2-1
- Version 0.2
- Fix URL
- Comply with fedora extras specfile format.
- Depend on python-elementtree and python-kid -- the names in extras.

* Thu Mar 03 2005 Konstantin Ryabitsev <icon@linux.duke.edu> 0.1-1
- Initial build
