Name:           repoview
Version:        0.7.1
Release:        1%{?dist}
Summary:        Creates a set of static HTML pages in a yum repository

License:        GPLv2+
URL:            https://github.com/sergiomb2/repoview
Source0:        https://github.com/sergiomb2/repoview/archive/v%{version}/%{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3 >= 3.5
Requires:       python3-genshi >= 0.6.3
Requires:       python3-libcomps
Requires:       python3-rpm

%description
RepoView creates a set of static HTML pages in a yum/dnf repository for easy
browsing.


%prep
%setup -q


%build


%install
mkdir -p -m 755                         \
    $RPM_BUILD_ROOT/%{_datadir}/%{name} \
    $RPM_BUILD_ROOT/%{_bindir}          \
    $RPM_BUILD_ROOT/%{_mandir}/man8
install -p -m 755 repoview.py  $RPM_BUILD_ROOT/%{_bindir}/repoview
install -p -m 644 repoview.8   $RPM_BUILD_ROOT/%{_mandir}/man8/
cp -rp templates               $RPM_BUILD_ROOT/%{_datadir}/%{name}/


%files
%doc README COPYING ChangeLog
%{_datadir}/%{name}
%{_bindir}/*
%{_mandir}/man*/*


%changelog
* Thu Oct 23 2025 Sérgio Basto <sergio@serjux.com> - 0.7.1-1
- Update to 0.7.1

* Mon Oct 13 2025 Sérgio Basto <sergio@serjux.com> - 0.7.0-9
- Python 3 beta version

* Mon Oct 13 2025 Sérgio Basto <sergio@serjux.com> - 0.7.0-8
- Python 3 alpha version

* Fri Oct 3 2025 Stephen Collier <stephenbcollier@gmail.com> - 0.7.0-7
- fix some typos

* Thu Oct 2 2025 Stephen Collier <stephenbcollier@gmail.com> - 0.7.0
- Rebuilt for python3

* Sun May 16 2021 Sérgio Basto <sergio@serjux.com> - 0.6.7-1
- Update to 0.6.7

* Sat Mar 14 2020 josef radinger <cheese@nosuchhost.net> - 0.6.6-15
- rebuild for fedora 31
- Require python2-rpmUtils
- force python2

* Sat Feb 02 2019 Fedora Release Engineering <releng@fedoraproject.org> - 0.6.6-14
- Rebuilt for https://fedoraproject.org/wiki/Fedora_30_Mass_Rebuild

* Sat Jul 14 2018 Fedora Release Engineering <releng@fedoraproject.org> - 0.6.6-13
- Rebuilt for https://fedoraproject.org/wiki/Fedora_29_Mass_Rebuild

* Wed Feb 14 2018 Iryna Shcherbina <ishcherb@redhat.com> - 0.6.6-12
- Update Python 2 dependency declarations to new packaging standards
  (See https://fedoraproject.org/wiki/FinalizingFedoraSwitchtoPython3)

* Fri Feb 09 2018 Fedora Release Engineering <releng@fedoraproject.org> - 0.6.6-11
- Rebuilt for https://fedoraproject.org/wiki/Fedora_28_Mass_Rebuild

* Thu Jul 27 2017 Fedora Release Engineering <releng@fedoraproject.org> - 0.6.6-10
- Rebuilt for https://fedoraproject.org/wiki/Fedora_27_Mass_Rebuild

* Sat Feb 11 2017 Fedora Release Engineering <releng@fedoraproject.org> - 0.6.6-9
- Rebuilt for https://fedoraproject.org/wiki/Fedora_26_Mass_Rebuild

* Thu Feb 04 2016 Fedora Release Engineering <releng@fedoraproject.org> - 0.6.6-8
- Rebuilt for https://fedoraproject.org/wiki/Fedora_24_Mass_Rebuild

* Thu Jun 18 2015 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.6.6-7
- Rebuilt for https://fedoraproject.org/wiki/Fedora_23_Mass_Rebuild

* Sun Jun 08 2014 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.6.6-6
- Rebuilt for https://fedoraproject.org/wiki/Fedora_21_Mass_Rebuild

* Sun Aug 04 2013 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.6.6-5
- Rebuilt for https://fedoraproject.org/wiki/Fedora_20_Mass_Rebuild

* Thu Feb 14 2013 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.6.6-4
- Rebuilt for https://fedoraproject.org/wiki/Fedora_19_Mass_Rebuild

* Sat Jul 21 2012 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.6.6-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_18_Mass_Rebuild

* Sat Jan 14 2012 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.6.6-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_17_Mass_Rebuild

* Wed Nov 16 2011 Konstantin Ryabitsev <icon@fedoraproject.org> - 0.6.6-1
- Update to 0.6.6 (bugfixes)

* Wed Feb 09 2011 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.6.5-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_15_Mass_Rebuild

* Fri Feb 19 2010 Konstantin Ryabitsev <icon@fedoraproject.org> - 0.6.5-1
- Update to 0.6.5 (bugfixes)

* Wed Jan 27 2010 Konstantin Ryabitsev <icon@fedoraproject.org> - 0.6.4-1
- Update to 0.6.4 (bugfixes)

* Sun Jul 26 2009 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.6.3-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_12_Mass_Rebuild

* Fri Mar 27 2009 Konstantin Ryabitsev <icon@fedoraproject.org> - 0.6.3-1
- Upstream 0.6.3
- Upstream fix for mixed-case packages and md5 warnings (obsoletes patch)
- Minor fixes to functionality

* Thu Mar 26 2009 Seth Vidal <skvidal at fedoraproject.org>
- don't lowercase pkgnames
- stop md5 warning emit

* Wed Feb 25 2009 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.6.2-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_11_Mass_Rebuild

* Sat Feb 02 2008 Konstantin Ryabitsev <icon@fedoraproject.org> - 0.6.2-1
- Upstream 0.6.2
- Modify URLs to point to the new repoview home

* Thu Oct 25 2007 Seth Vidal <skvidal at fedoraproject.org> - 0.6.1-2
- add fedora repoview templates

* Thu Sep 27 2007 Konstantin Ryabitsev <icon@fedoraproject.org> - 0.6.1-1
- Upstream 0.6.1
- Adjust license to GPLv2+

* Thu Jul 19 2007 Konstantin Ryabitsev <icon@fedoraproject.org> - 0.6.0-1
- Upstream 0.6.0
- Drop obsolete patch

* Tue Jul 04 2006 Konstantin Ryabitsev <icon@fedoraproject.org> - 0.5.2-1
- Version 0.5.2
- Use yum-2.9 API patch (Jesse Keating)

* Wed Feb 15 2006 Konstantin Ryabitsev <icon@fedoraproject.org> - 0.5.1-1
- Version 0.5.1

* Fri Jan 13 2006 Konstantin Ryabitsev <icon@fedoraproject.org> - 0.5-1
- Version 0.5

* Sun Oct 09 2005 Konstantin Ryabitsev <icon@linux.duke.edu> - 0.4.1-1
- Version 0.4.1

* Fri Sep 23 2005 Konstantin Ryabitsev <icon@linux.duke.edu> - 0.4-1
- Version 0.4
- Require yum >= 2.3
- Drop requirement for python-elementtree, since it's required by yum
- Disttagging.

* Mon Apr 04 2005 Konstantin Ryabitsev <icon@linux.duke.edu> 0.3-3
- Do not BuildRequire sed -- basic enough dependency, even for version 4.

* Tue Mar 29 2005 Konstantin Ryabitsev <icon@linux.duke.edu> 0.3-2
- Preserve timestamps on installed files
- Do not use macros in source tags
- Omit Epoch

* Fri Mar 25 2005 Konstantin Ryabitsev <icon@linux.duke.edu> 0.3-1
- Version 0.3

* Thu Mar 10 2005 Konstantin Ryabitsev <icon@linux.duke.edu> 0.2-1
- Version 0.2
- Fix URL
- Comply with fedora extras specfile format.
- Depend on python-elementtree and python-kid -- the names in extras.

* Thu Mar 03 2005 Konstantin Ryabitsev <icon@linux.duke.edu> 0.1-1
- Initial build
