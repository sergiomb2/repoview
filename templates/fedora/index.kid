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
    <link py:if="url is not None"
       rel="alternate" type="application/rss+xml" title="RSS" href="latest-feed.xml" />
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
        <h3>Latest packages:</h3>
        <ul>
          <li py:for="(name, filename, version, release, built) in latest">
            <em><span py:content="ymd(built)"/></em>:
            <a href="${filename}" class="inpage"
                py:content="'%s-%s-%s' % (name, version, release)"/>
          </li>
        </ul>

        <h3>Available Groups</h3>
        <ul>
          <li py:for="(name, filename, description, packages) in groups">
            <a href="${filename}" class="inpage"
                py:content="name"/>
          </li>
        </ul>

   </div>
   </div>    
    <div id="bottom">
      <div id="footer">
        <p>
          <span py:content="'Listing generated: %s by' % ymd(time.time())"/>
          <a href="https://github.com/sergiomb2/repoview"
            class="repoview" py:content="'RepoView-%s' % repo_data['my_version']"/>
        </p>
       
      </div>
    </div>
  </body>
</html>




