# $Id$

%define _pyver   %(python -c 'import sys; print sys.version[:3],')

%define _python  %{_bindir}/python%{_pyver}
%define _pydir   %{_libdir}/python%{_pyver}/site-packages

#------------------------------------------------------------------------------

Summary:        Creates a set of static HTML pages in a yum repository.
Name:           repoview
Version:        0.1
Release:        1.%{_pyver}
Epoch:          0
License:        GPL
Group:          Applications/System
Source:         http://linux.duke.edu/projects/mini/%{name}/download/%{name}-%{version}.tar.gz
URL:            http://linux.duke.edu/projects/%{name}
BuildRoot:      %{_tmppath}/%{name}-%{version}-root
BuildArch:      noarch
BuildPrereq:    %{_python}, perl
Requires:       %{_python}, kid = 0.5, elementtree

%description
RepoView creates a set of static HTML pages in a yum repository for easy
browsing.

#------------------------------------------------------------------------------

%prep
%setup -q
##
# Fix version and default templates dir.
#
%{__perl} -pi -e \
    "s/^VERSION\s*=\s*.*/VERSION = '%{version}-%{release}'/g" repoview
%{__perl} -pi -e \
    "s/^DEFAULT_TEMPLATEDIR\s*=.*/DEFAULT_TEMPLATEDIR = '%{_datadir}/%{name}/templates'/g" \
    repoview

#------------------------------------------------------------------------------

%install
%{__rm} -rf %{buildroot}
%{__mkdir_p} -m 755 \
    %{buildroot}/%{_datadir}/%{name} \
    %{buildroot}/%{_bindir}
%{__install} -m 755 repoview %{buildroot}/%{_bindir}/repoview
%{__cp} -rp templates %{buildroot}/%{_datadir}/%{name}/

#------------------------------------------------------------------------------

%clean
%{__rm} -rf %{buildroot}

#------------------------------------------------------------------------------

%files
%defattr(-,root,root,-)
%doc README COPYING
%{_datadir}/%{name}
%{_bindir}/*

#------------------------------------------------------------------------------

%changelog
* Thu Mar 03 2005 Konstantin Ryabitsev <icon@linux.duke.edu> 0.1-1
- Initial build
