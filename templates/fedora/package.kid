<?xml version="1.0" encoding="utf-8"?>
<?python
import time
def ymd(stamp):
    return time.strftime('%Y-%m-%d', time.localtime(int(stamp)))
?>

<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns:py="http://genshi.edgewall.org/">
  <head>
    <title py:content="'RepoView: %s' % repo_data['title']"/>
    <style type="text/css" media="screen">
      @import url("layout/fedora.css");
      @import url("layout/pkgdb.css");
      @import url("layout/style.css");
    </style>
    <meta name="robots" content="noindex,follow" />
  </head>

  <body>
    <div id="wrapper">
      <div id="head">
        <h1><a href="http://fedoraproject.org/index.html">Fedora</a></h1>
      </div>
   
       <div id="content">
          <p class="nav">Jump to letter: [
          <span class="letterlist">
            <a py:for="letter in repo_data['letters']"
              class="nlink"
              href="${'letter_%s.group.html' % letter.lower()}" py:content="letter"/>
          </span>]
        </p>   
    <h2>${pkg_data['name']} - ${pkg_data['summary']}</h2>
    <ul class="actions">
      <li><a class="koji" href="http://koji.fedoraproject.org/koji/search?type=package&amp;terms=${pkg_data['name']}&amp;match=glob">Build Status</a></li>
      <li><a class="bodhi" href="https://admin.fedoraproject.org/updates/${pkg_data['name']}">Update Status</a></li>
      <li><a class="bug_list" href="http://bugz.fedoraproject.org/${pkg_data['name']}">Bug Reports</a></li>
      <li><a class="pkgdb" href="https://admin.fedoraproject.org/pkgdb/packages/name/${pkg_data['name']}">Packagedb</a></li>
    </ul>

    <p>Description: <pre>${pkg_data['description']}</pre></p>
    <p>Homepage: <a href="${pkg_data['url']}">${pkg_data['url']}</a></p>
    <p py:if="pkg_data['rpm_license']">License: ${pkg_data['rpm_license']}</p>
    <p py:if="pkg_data['vendor']">Vendor: ${pkg_data['vendor']}</p>

    <h3>Packages</h3>
    <table border="0" cellpadding="0" cellspacing="10">
      <tr py:for="(e, v, r, a, built, size, loc, author, log, added) in pkg_data['rpms']">
         <td valign="top"><a href="${'../%s' % loc}" class="inpage" py:content="'%s-%s-%s.%s' % (pkg_data['name'], v, r, a)"/>
          [<span style="white-space: nowrap" py:content="size"/>]</td>
         <td valign="top" py:if="log">
           <strong>Changelog</strong> by <span py:content="'%s (%s)' % (author, ymd(added))"/>:
              <pre style="margin: 0pt 0pt 5pt 5pt" py:content="log"/>
         </td>
         <td valign="top" py:if="not log">
          	<em>(no changelog entry)</em>
         </td>
      </tr>
    </table>
   </div>
   </div>    
    <div id="bottom">
      <div id="footer">
        <p class="copy">
        Copyright © 2007 Red Hat, Inc. and others.  All Rights Reserved.
        Please send any comments or corrections to the <a href="mailto:webmaster@fedoraproject.org">websites team</a>.
        </p>

        <p class="disclaimer">
        The Fedora Project is maintained and driven by the community and sponsored by Red Hat.  This is a community maintained site.  Red Hat is not responsible for content.
        </p>
        <ul>
          <li class="first"><a href="http://fedoraproject.org/wiki/Legal">Legal</a></li>
          <li><a href="http://fedoraproject.org/wiki/Legal/TrademarkGuidelines">Trademark Guidelines</a></li>
        </ul>
      </div>
    </div>
  </body>
</html>
