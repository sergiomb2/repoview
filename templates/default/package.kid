<?xml version="1.0" encoding="utf-8"?>
<?python
import time
def ymd(stamp):
    return time.strftime('%Y-%m-%d', time.localtime(int(stamp)))
?>
<html xmlns:py="http://purl.org/kid/ns#">
<head>
  <title py:content="'RepoView: %s' % repo_data['title']"/>
  <link rel="stylesheet" href="layout/repostyle.css" type="text/css"/>
  <meta name="robots" content="noindex,follow" />
</head>
<body>
    <div class="levbar">
      <p class="pagetitle" py:content="group_data['name']"/>
      <ul class="levbarlist">
        <li>
        <a href="${group_data['filename']}" 
            title="Back to package listing"
            class="nlink">&laquo; Back to group</a>
    </li>
    </ul>

    </div>
    <div class="main">
        <p class="nav">Jump to letter: [
          <span class="letterlist">
            <a py:for="letter in repo_data['letters']"
              class="nlink"
              href="${'letter_%s.group.html' % letter.lower()}" py:content="letter"/>
          </span>]
        </p>
        <h2 py:content="'%s - %s' % (pkg_data['name'], pkg_data['summary'])"/>
        
        <table border="0" cellspacing="0" cellpadding="2">
          <tr py:if="pkg_data['url']">
            <th>Website:</th>
            <td><a href="${pkg_data['url']}" py:content="pkg_data['url']"/></td>
          </tr>
          <tr py:if="pkg_data['rpm_license']">
            <th>License:</th>
            <td py:content="pkg_data['rpm_license']"/>
          </tr>
          <tr py:if="pkg_data['vendor']">
            <th>Vendor:</th>
            <td py:content="pkg_data['vendor']"/>
          </tr>
        </table>

        <dl>
        <dt>Description:</dt>
        <dd><pre py:content="pkg_data['description']"/></dd>
        </dl>

        <h3>Packages</h3>
        <table border="0" cellpadding="0" cellspacing="10">
        <tr py:for="(e, v, r, a, built, size, loc, author, log, added) in pkg_data['rpms']">
            <td valign="top"><a href="${'../%s' % loc}" class="inpage" 
              py:content="'%s-%s-%s.%s' % (pkg_data['name'], v, r, a)"/>
              [<span style="white-space: nowrap" py:content="size"/>]</td>
            <td valign="top" py:if="log">
              <strong>Changelog</strong>
              by <span py:content="'%s (%s)' % (author, ymd(added))"/>:
              <pre style="margin: 0pt 0pt 5pt 5pt" py:content="log"/>
            </td>
            <td valign="top" py:if="not log">
            	<em>(no changelog entry)</em>
            </td>
        </tr>
        </table>
        <p class="footernote">
          Listing created by
          <a href="https://fedorahosted.org/repoview/"
            class="repoview" py:content="'Repoview-%s' % repo_data['my_version']"/>
        </p>
    </div>
</body>
</html>
