# $Id$

Summary:        Creates a set of static HTML pages in a yum repository.
Name:           repoview
Version:        0.1
Release:        1
Epoch:          0
License:        GPL
Group:          Applications/System
Source:         http://linux.duke.edu/projects/mini/%{name}/download/%{name}-%{version}.tar.gz
URL:            http://linux.duke.edu/projects/%{name}
BuildRoot:      %{_tmppath}/%{name}-%{version}-root
BuildArch:      noarch
BuildPrereq:    sed
Requires:       python >= 2.2, kid >= 0.5, kid < 0.6, elementtree

%description
RepoView creates a set of static HTML pages in a yum repository for easy
browsing.

#------------------------------------------------------------------------------

%prep
%setup -q
##
# Fix version and default templates dir.
#
%{__sed} -i -e \
    "s|^VERSION =.*|VERSION = '%{version}-%{release}'|g" repoview
%{__sed} -i -e \
    "s|^DEFAULT_TEMPLATEDIR =.*|DEFAULT_TEMPLATEDIR = '%{_datadir}/%{name}/templates'|g" \
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
